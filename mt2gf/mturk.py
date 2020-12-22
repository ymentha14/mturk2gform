"""
Script to automate the creation and handling of MTurk task: it assumes you have a gform_map.txt file
pointing to Google forms as describe in the README.


"""
import pickle as pk
from datetime import datetime
from pathlib import Path

import boto3
import pandas as pd
import pytz
import xmltodict

from mt2gf.gform import download_csv, download_multi_csv
from mt2gf.utils import read_access_keys

# from mt2gf.fraudulous import detect_repeat_frauders,detect_honey_frauders


utc = pytz.UTC


def create_mturk_client(aws_access_key_id, aws_secret_access_key, production=False):
    """
    Return an MTURK client.
    Inspired from https://blog.mturk.com/tutorial-mturk-using-python-in-jupyter-notebook-17ba0745a97f

    Args:
        aws_access_key_id (str): aws key
        aws_secret_access_key (str): secret aws key
        production (Bool): sandbox if set to false

    Returns:
        client (boto3.client): low level boto3 object allowing for HITs manipulation
    """
    create_hits_in_production = production
    environments = {
        "production": {
            "endpoint": "https://mturk-requester.us-east-1.amazonaws.com",
            "preview": "https://www.mturk.com/mturk/preview",
        },
        "sandbox": {
            "endpoint": "https://mturk-requester-sandbox.us-east-1.amazonaws.com",
            "preview": "https://workersandbox.mturk.com/mturk/preview",
        },
    }
    mturk_environment = (
        environments["production"]
        if create_hits_in_production
        else environments["sandbox"]
    )

    client = boto3.client(
        "mturk",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name="us-east-1",
        endpoint_url=mturk_environment["endpoint"],
    )
    return client


def get_answer(answer):
    """
    Parse the text out of an answer

    Args:
        answer (dict): as returned by Assignment['Answer']
    """
    xml_doc = xmltodict.parse(answer)
    return xml_doc["QuestionFormAnswers"]["Answer"]["FreeText"]


class MTurkParam:
    """
    Parameter object for the Turker instances: all parameters in ThisFormat
    end up in boto3 call, in contrast to this_format, used for other tasks.
    """

    def __init__(
        self,
        aws_key_path,
        hit_layout,
        MaxAssignments,
        LifetimeInDays,
        AutoApprovalDelayInDays,
        AssignmentDurationInSeconds,
        QualificationRequirements,
        Reward,
        HITTitle,
        Keywords,
        Description,
        production=False,
    ):
        """
        For appropriate arguments, please visit `[boto3 reference] <http://stackoverflow.com/>` for an in-depth description.

        Args:
            aws_key_path (str): path to the AWS access key file: that is, the aws.csv file with public and private key
            hitlayout (str): hitlayout of the template to use
            MaxAssignments (int): [boto3 reference] The number of times the HIT can be accepted and completed before the HIT becomes unavailable.
            LifetimeInDays (float): [boto3 reference] An amount of time, in DAYS, after which the HIT is no longer available for users to accept. After the lifetime of the HIT elapses, the HIT no longer appears in HIT searches, even if not all of the assignments for the HIT have been accepted.
            AutoApprovalDelayInDays (float): [boto3 reference] The number of DAYS after an assignment for the HIT has been submitted, after which the assignment is considered Approved automatically unless the Requester explicitly rejects it.
            AssignmentDurationInSeconds (float): [boto3 reference] The amount of time, in seconds, that a Worker has to complete the HIT after accepting it. If a Worker does not complete the assignment within the specified duration, the assignment is considered abandoned. If the HIT is still active (that is, its lifetime has not elapsed), the assignment becomes available for other users to find and accept.
            QualificationRequirements (list): [boto3 reference] Conditions that a Worker's Qualifications must meet in order to accept the HIT. A HIT can have between zero and ten Qualification requirements. All requirements must be met in order for a Worker to accept the HIT. Additionally, other actions can be restricted using the ActionsGuarded field on each QualificationRequirement structure.
            Reward (str): [boto3 reference] A string representing a currency amount.
            HITTitle (str): [boto3 reference] The title of the HIT. A title should be short and descriptive about the kind of task the HIT contains. On the Amazon Mechanical Turk web site, the HIT title appears in search results, and everywhere the HIT is mentioned.
            Keywords (str):  [boto3 reference] One or more words or phrases that describe the HIT, separated by commas. These words are used in searches to find HITs.
            Description (str): [boto3 reference] A general description of the HIT. A description includes detailed information about the kind of task the HIT contains. On the Amazon Mechanical Turk web site, the HIT description appears in the expanded view of search results, and in the HIT and assignment screens. A good description gives the user enough information to evaluate the HIT before accepting it.
            production (Bool): set to False in order to use the MTurk Sandbox, True otherwise
        """
        self.aws_key_path = aws_key_path

        self.MaxAssignments = MaxAssignments
        self.LifetimeInSeconds = int(LifetimeInDays * 3600 * 24)
        self.AutoApprovalDelayInSeconds = int(AutoApprovalDelayInDays * 3600 * 24)
        self.AssignmentDurationInSeconds = AssignmentDurationInSeconds
        self.Reward = Reward
        self.HITTitle = HITTitle
        self.Keywords = Keywords
        self.Description = Description
        self.hit_layout = hit_layout
        self.cost = self.MaxAssignments * float(self.Reward)
        self.QualificationRequirements = QualificationRequirements
        self.production = production
        self.url = (
            "https://worker.mturk.com/mturk/preview?groupId="
            if self.production
            else "https://workersandbox.mturk.com/mturk"
        )

    def __repr__(self):
        return (
            f"MaxAss:{self.MaxAssignments} Lifetime:{self.LifetimeInSeconds} "
            + f"Autoapprov:{self.AutoApprovalDelayInSeconds} Reward:{self.Reward} "
            + f"AssignDuration:{self.AssignmentDurationInSeconds}"
        )


class Turker:
    """
    Class to perform
    """

    def __init__(
        self,
        meta_dir,
        param,
        gservice,
        gform_map,
        formresdir,
        conf_code_generator=None,
        frauder_callbacks=[],
        check_conf_code=False,
        check_code_frauders=False,
    ):
        """
        Args:
            meta_dir (str): path where the Turker can create a ".mt2gf" directory to store metadata
            about the run, allowing it to reload in case of program crash/interruption.
            param (mt2gf.MTurkParam): parameter for the run, cf documentation for MTurkParam
            gservice (googleapiclient.discovery.Resource): as returned by mt2gf.auto_drive.get_drive_service
            gform_map (dict): as returned by mt2gf.auto_drive.get_gform_map or mt2gf.auto_drive.get_batch_gform_map
            formresdir (str): directory where to store the results, that is, the csv version of the google spreadsheets
            containing the results of the Google forms. In case of batching, formresdir must point to the digit directory
            corresponding to the current batch (cf mt2gf.preprocess.get_batch_indexes)
            conf_code_generator (func): function returning a confirmation code (str) composed of 3 digits given a form index
            as argument (int).
            If set to None, no check will be performed on the confirmation code.
            WARNING: when using this feature, make sure that the output of this function is systematically
            equal to the codes generated in the google forms! I
            frauder_callbacks (list of func): list of functions detecting frauders, that is WorkerIDs that need to be rejected
            for a given HIT. Each such function takes as single argument a pd.DataFrame corresponding to this HIT as returned by mt2gf.Turker.get_results
            (that is, a pd.DataFrame whose columns are equal to the google forms questions fields) and returns a set of string consisting
            of the Worker IDs whose Assignment must be rejected for the given HIT.
            check_code_frauders (Bool): If set to True, Turker.approve_correct_assignments and Turker.approve_correct_hits will reject any WorkerId present
            in an MTurk HIt but absent of the Google form. This makes sure that no HIT will be validated without data in the Google Form.
            NB: Worker entering a malformed ID are rejected as well
        """
        # Mturk Parameters
        self.p = param
        print(f"Estimated cost:{self.p.cost * len(gform_map):.2f} $")

        # Metadata initialization
        meta_dir = Path(meta_dir)
        meta_dir = meta_dir.joinpath(".mt2gf")
        meta_dir.mkdir(exist_ok=True)
        if self.p.production:
            self.hit2form_path = meta_dir.joinpath("hit2form.pk")
        else:
            self.hit2form_path = meta_dir.joinpath("hit2formsandbox.pk")
        self.watcher_process = None
        self.gservice = gservice
        self.gform_map = gform_map
        self.formresdir = Path(formresdir)
        self.conf_code_generator = conf_code_generator
        self.frauder_callbacks = frauder_callbacks
        self.check_conf_code = conf_code_generator is not None
        self.check_code_frauders = check_code_frauders

        # Retrieval of the access keys
        aws_access_key_id, aws_secret_access_key = read_access_keys(self.p.aws_key_path)
        self.client = create_mturk_client(
            aws_access_key_id, aws_secret_access_key, self.p.production
        )

        # Creation of an Mturk client
        if self.hit2form_path.exists():
            self.hit2form = pk.load(open(self.hit2form_path, "rb"))
        else:
            self.hit2form = {}

        # Download a first version of the Google forms
        download_multi_csv(gform_map, self.formresdir, gservice)

    def list_reviewable_hits(self):
        """
        List the HITs in a reviwable state
        """
        hits = [hit for hit in self.client.list_reviewable_hits()["HITs"]]
        if len(hits) == 0:
            print("No reviewable hit available")
        return hits

    def list_hits(self):
        """
        Published HITs informations: HITId,Status,Completed,Percent_completed
        Completed designates the number of completed forms for the given HIT.
        Once Percent_completed reaches 100, the HIT status becomes "Assignable"

        Returns:
            [pd.DataFrame]: Dataframe with HITId,Status,Completed,Percent_completed columns
        """
        hits = self.client.list_hits()["HITs"]
        if len(hits) == 0:
            print("No Hits available")
        else:
            expiration = hits[0]["Expiration"].replace(tzinfo=utc)
            now = datetime.now().replace(tzinfo=utc)
            if expiration < now:
                print("EXPIRED")
            else:
                delay = expiration - now
                delay = int(delay.total_seconds()) / 60
                print(
                    f"Expiration:{expiration.strftime('%b %d %Y %H:%M:%S')} ({delay:.2f} minutes left)"
                )
                print(f"{self.p.url}")
            df = []
            for hit in hits:
                row = {}
                hitid = hit["HITId"]
                row["FormIdx"] = self.hit2form.get(hitid, 9999)
                row["HITId"] = hitid
                row["Status"] = hit["HITStatus"]
                comp = self.client.list_assignments_for_hit(
                    HITId=hitid,
                    AssignmentStatuses=["Submitted", "Approved", "Rejected"],
                )["NumResults"]
                row["Completed"] = comp
                maxo = hit["MaxAssignments"]
                row["Percent_completed"] = int(comp / maxo * 100)
                df.append(row)
            df = pd.DataFrame(df).set_index("FormIdx").sort_index()
            return df

    def create_forms_hits(
        self,
    ):
        """
        Generate and publish the HITs corresponding to the forms whose index
        are present in Turker.gform_map
        """
        for idx, url in [(idx, val["url"]) for idx, val in self.gform_map.items()]:
            print(f"Creating hit for form {idx}")

            myhit = self.client.create_hit(
                MaxAssignments=self.p.MaxAssignments,
                LifetimeInSeconds=self.p.LifetimeInSeconds,
                AutoApprovalDelayInSeconds=self.p.AutoApprovalDelayInSeconds,
                AssignmentDurationInSeconds=self.p.AssignmentDurationInSeconds,
                Reward=self.p.Reward,
                HITLayoutId=self.p.hit_layout,
                HITLayoutParameters=[{"Name": "url", "Value": url}],
                Title=f"{self.p.HITTitle} {idx}",
                Keywords=self.p.Keywords,
                Description=self.p.Description,
                QualificationRequirements=self.p.QualificationRequirements,
            )
            self.hit2form[myhit["HIT"]["HITId"]] = idx
        self.__update_hit2form()
        print(f"Hits available on {self.p.url}")

    def get_results(self, id):
        """
        Download and return the most recent version of the Google Forms results corresponding to id (HITid or Google form index)
        as a pd.Dataframe ()

        Args:
            id (int or str): if int, must correspond to the index of the Google form. If string, must correspond to a valid HIT id

        Returns:
            [pd.DataFrame]: results: data filled by the MTurk Workers
        """
        try:
            if type(id) == str:
                if id.isdigit():
                    form_idx = int(id)
                else:
                    form_idx = self.hit2form[id]
            gid = self.gform_map[form_idx]["driveid"]
        except KeyError:
            raise KeyError("Invalid form index/ hit id")
        path = self.formresdir.joinpath(f"{form_idx}.csv")
        download_csv(path, gid, self.gservice, verbose=True)
        df = pd.read_csv(path)
        return df

    def list_assignments(self, hit_id):
        """
        Return all the assignments corresponding to the given hit_id

        Args:
            hit_id (str): MTurk valid HIT id

        Returns:
            [pd.DataFrame]: Columns WorkerId,HITId,FormId,ConfCode,AcceptTime,SubmitTime,TrueConfCode,Status
        """
        worker_results = self.client.list_assignments_for_hit(
            HITId=hit_id, AssignmentStatuses=["Submitted", "Approved", "Rejected"]
        )
        if worker_results["NumResults"] > 0:
            df = []
            for assignment in worker_results["Assignments"]:
                answer = get_answer(assignment["Answer"])
                if self.check_conf_code:
                    conf_code = self.conf_code_generator(self.hit2form[hit_id])
                else:
                    conf_code = None
                df.append(
                    {
                        "WorkerId": assignment["WorkerId"],
                        "HITId": hit_id,
                        "FormId": self.hit2form[hit_id],
                        "ConfCode": answer,
                        "AcceptTime": assignment["AcceptTime"],
                        "SubmitTime": assignment["SubmitTime"],
                        "TrueConfCode": conf_code,
                        "Status": assignment["AssignmentStatus"],
                    }
                )
            df = pd.DataFrame(df)
            return df
        else:
            print(f"No results ready yet for {hit_id}")
            return None

    def list_all_assignments(self):
        """
        List all assignments for all hits. Cf Turker.list_assignments

        Returns:
            [pd.DataFrame]: Concatenation of the dataframe returned by list_assignments for all HITs.
        """
        df = []
        hits = self.client.list_hits()["HITs"]
        if len(hits) == 0:
            print("No results")
            return pd.DataFrame()
        for hit in hits:
            hit_id = hit["HITId"]
            assignment = self.list_assignments(hit_id)
            if assignment is not None:
                df.append(assignment)
        if len(df) == 0:
            return pd.DataFrame()
        df = pd.concat(df, axis=0)
        return df

    def save_worker_infos(self, directory=None):
        """
        Save the workers metadata (completion time etc)

        Args:
            directory (str): directory in which the worker infos will be saved. Defaults
            to the formresdir directory.
        """
        # Default directory
        directory = Path(directory)
        if directory is None:
            directory = self.formresdir
        df = self.list_all_assignments()

        # If no assignments are ready yet
        if df.shape[0] == 0:
            return None

        # We have at least one assignment
        df = df[["WorkerId", "FormId", "AcceptTime", "SubmitTime"]]
        df["AnswerDurationInSeconds"] = (df["SubmitTime"] - df["AcceptTime"]).dt.seconds
        df.drop(columns=["AcceptTime", "SubmitTime"], inplace=True)

        workers_infos_path = directory.joinpath("workers_info.csv")

        # append mode if some information was already here
        if workers_infos_path.exists():
            old_df = pd.read_csv(workers_infos_path)
            df = pd.concat([old_df, df], axis=0)
            # we get rid of potential duplicates
            df.drop_duplicates(inplace=True)

        df.to_csv(workers_infos_path, index=False)

    def approve_correct_assignments(
        self, hit_id, callbacks=None, check_code_frauders=None, dry_run=False
    ):
        """
        Approve assignments in Reviewable state corresponding to the provided HIT id.

        Args:
            hit_id (str): MTurk HIT id
            callbacks (list of func): If value is set, overrides self.frauder_callbacks.
            List of functions detecting frauders, that is WorkerIDs that need to be rejected
            for a given HIT. Each such function takes as single argument a pd.DataFrame corresponding to this HIT as returned by mt2gf.Turker.get_results
            (that is, a pd.DataFrame whose columns are equal to the google forms questions fields) and returns a set of string consisting
            of the Worker IDs whose Assignment must be rejected for the given HIT.
            check_code_frauders (Bool): If value is set, overrides self.check_code_frauders. When set to True, will reject any WorkerId present
            in an MTurk HIt but absent of the Google form. This makes sure that no HIT will be validated without data in the Google Form.
            NB: Worker entering a malformed ID are rejected as well
            dry_run (Bool): if set to True, no HIT will be effectively validated or rejected: the output
        """

        # Function argument override class attributes
        if callbacks is None:
            callbacks = self.frauder_callbacks
        if check_code_frauders is None:
            check_code_frauders = self.check_code_frauders

        run_conditions = [
            len(callbacks) == 0,
            not self.check_conf_code,
            not check_code_frauders,
        ]

        if all(run_conditions):
            raise ValueError(
                "No condition was defined to determine correct assignments: set the callbacks value to approve_correct_assignments or one of check_conf_code or check_code_frauders"
            )

        # Convert the hit id to a form index
        form_idx = self.hit2form[hit_id]

        assignments = self.client.list_assignments_for_hit(
            HITId=hit_id, AssignmentStatuses=["Submitted"]
        )["Assignments"]

        frauders_data = self.__build_frauders_data(
            form_idx, assignments, callbacks, check_code_frauders
        )

        # We iterate over the assignments and check for frauders
        for assignment in assignments:
            ass_id = assignment["AssignmentId"]
            worker_id = assignment["WorkerId"]
            reject, requester_feedback = self.__detect_fraudulous_worker(
                worker_id, frauders_data
            )
            if reject:
                print(f"Reject wid {worker_id} hitid {hit_id} formidx {form_idx}")
                print(requester_feedback)
                if not dry_run:
                    self.client.reject_assignment(
                        AssignmentId=ass_id, RequesterFeedback=requester_feedback
                    )
            else:
                print(f"Approve wid {worker_id} hitid {hit_id} formidx {form_idx}")
                if not dry_run:
                    self.client.approve_assignment(AssignmentId=ass_id)

    def __detect_fraudulous_worker(self, worker_id, frauders_data):
        """
        Helper function for Turker.approve_correct_assignments.

        Args:
            cf approve_correct_assignments

        Returns:
            (bool): whether the worker needs to be rejected
            (str): corresponding feedback citingthe reason(s) for the rejection
        """
        requester_feedback = ""
        reject = False
        for frauder_data in frauders_data:
            frauders = frauder_data["frauders"]
            msg = frauder_data["feedback"]
            if worker_id in frauders:
                requester_feedback += msg + "\n"
                reject = True
        return reject, requester_feedback

    def __build_frauders_data(
        self, form_idx, assignments, callbacks, check_code_frauders
    ):
        """
        Helper function for Turker.approve_correct_assignments.

        Args:
            cf approve_correct_assignments

        Returns:
            [list of dict]: each dict has an 'frauders' entry (set of string corresponding to WorkerID to reject for the HIT)
            and 'feedback' entry (Why the given worker needs to be rejected)
        """
        # Path where to store the results
        form_path = self.formresdir.joinpath(f"{form_idx}.csv")
        drive_id = self.gform_map[form_idx]["driveid"]

        # Ensure we have the latest version for this given file
        download_csv(form_path, drive_id, self.gservice)
        form_df = pd.read_csv(form_path)

        # Real MTurk worker ids
        workers = set([assignment["WorkerId"] for assignment in assignments])

        frauders_data = []
        # Check for valid confirmation code
        if self.check_conf_code:
            frauders = self.__detect_conf_code_frauders(
                assignments=assignments, conf_code=self.conf_code_generator(form_idx)
            )
            conf_code_frauders = {
                "frauders": frauders,
                "feedback": "Invalid confirmation code.",
            }
            frauders_data.append(conf_code_frauders)

        # Check for workers who entered a confirmation code but are not present in the gform data
        if check_code_frauders:
            workers_mturk = workers
            worker_gform = set(form_df["WorkerID"].unique())
            # Those workers who Gave an MTurk completion code but are not present in the Gform data
            # Prevent workers from sharing the completion code
            frauders = workers_mturk - worker_gform
            fake_id_frauders = {
                "frauders": frauders,
                "feedback": "Your Worker Id was not present in the form/Incorrectly spelled.",
            }
            frauders_data.append(fake_id_frauders)

        # User-defined callbacks
        for callback_func, callback_feedback in callbacks:
            frauders = callback_func(form_df)
            frauders_data.append({"frauders": frauders, "feedback": callback_feedback})
        return frauders_data

    def __detect_conf_code_frauders(self, assignments, true_conf_code):
        """
        Helper function for Turker.approve_correct_assignments: detects the confirmation
        code frauders

        Args:
            assignments: as returned by self.client.list_assignments_for_hit
            true_conf_code (str): true confirmation code

        Returns:
            [type]: [description]
        """
        conf_code_frauders = set()
        for assignment in assignments:
            worker_id = assignment["WorkerId"]
            answer = get_answer(assignment["Answer"])
            if answer != true_conf_code:
                conf_code_frauders.add(worker_id)
        return conf_code_frauders

    def approve_correct_hits(self, dry_run=False):
        """
        Approve all the HITs that don't violate any of the callback functions, reject the others.

        Args:
            dry_run (Bool): if set to True, no HIT will be effectively validated or rejected: the output
            remains the same for pre-checking the effect of a wet run.
        """
        hits = self.list_reviewable_hits()
        for hit in hits:
            self.approve_correct_assignments(hit["HITId"], dry_run=dry_run)

    def approve_all_assignments(self, hit_id):
        """
        Approve all assignments corresponding to the provided HIT id, regardless of
        their validity (No quality check or callbacks performed)
        If you wish to perform quality_check, cf approve_correct_assignments

        Args:
            correct_hits (Bool): whether to correct correct hits exclusively
        """
        assignments = self.client.list_assignments_for_hit(
            HITId=hit_id, AssignmentStatuses=["Submitted"]
        )
        assignments = assignments["Assignments"]
        for assignment in assignments:
            ass_id = assignment["AssignmentId"]
            # TODO: assignment['AcceptTime'/'SubmitTime']
            print(f"Approving assignment {ass_id}")
            self.client.approve_assignment(AssignmentId=ass_id)

    def approve_all_hits(self):
        """
        Approve all assignments of all HITs regardless of their validity (No quality
        check or callbacks performed)
        If you wish to perform quality_check, cf approve_correct_assignments
        """
        hits = self.list_reviewable_hits()
        for hit in hits:
            self.approve_all_assignments(hit["HITId"])

    def delete_all_hits(self):
        """
        Deletes all HITs having been been reviewed
        """
        hits = self.client.list_hits()["HITs"]
        for hit in hits:
            self.delete_hit(hit["HITId"])

    def delete_hit(self, hit_id):
        """
        Delete the hit hit_id from the Mturk platform.
        Fails in case the hit is not reviewed.

        Args:
            hit_id (str): Mturk HIT id
        """
        try:
            self.client.delete_hit(HITId=hit_id)
            print(f"Deleting hit {hit_id}")
            if hit_id in self.hit2form:
                del self.hit2form[hit_id]
                self.__update_hit2form()
        except:
            print(f"Can't delete {hit_id}. Is it reviewed?")

    def __update_hit2form(self):
        """
        Update the mapping between HIT ids and Google forms indexes
        """
        pk.dump(self.hit2form, open(self.hit2form_path, "wb"))

    def stop_hit(self, hit_id):
        """
        Update the expiration date of the hit at a past date.
        This allows the assignable hits to go to "Reviewable"
        state as soon as possible (lets the workers already working
        finish their task first)
        """
        # assert(hit_id in self.hit2form)
        status = self.client.get_hit(HITId=hit_id)["HIT"]["HITStatus"]
        # If HIT is active then set it to expire immediately
        if status == "Assignable" or status == "Unassignable":
            self.client.update_expiration_for_hit(
                HITId=hit_id, ExpireAt=datetime(2015, 1, 1)
            )
            print(f"Stop hit {hit_id}")

    def stop_all_hits(self):
        """
        Call Turker.stop_hit for every hit.
        """
        hits = self.client.list_hits()["HITs"]
        if len(hits) == 0:
            print("No HITs to stop")
        for hit in hits:
            self.stop_hit(hit["HITId"])
