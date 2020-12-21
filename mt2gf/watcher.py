import threading
from time import sleep

import pandas as pd
from botocore.exceptions import ClientError

from mt2gf.gform import download_multi_csv
from mt2gf.mturk import create_mturk_client
from mt2gf.utils import read_access_keys


class Watcher:
    """
    Class to monitor the workers who answer more than max_forms_per_worker forms
    in the pool. Once a worker reaches this limit, the watcher class who runs a subprocess
    tag the worker by granting him/her with an MTurk qualification that will prevent him/her
    to find any other form associated with the current pool.

    This allows to guarantee a certain MTurk workers diversity in the pool answerers.
    """

    def __init__(
        self,
        form_results_dir,
        gform_map,
        drive_service,
        aws_key_path,
        qualification_type_name="",
        qualification_description="",
        qualification_type_id=None,
        max_forms_per_worker=2,
        production=False,
    ):
        """
        Args:
            form_results_dir (pathlib Path): directory where to store the forms csv to analyze
            gform_map (dict):TODO complete
            drive_service: as returned by mt2gf.gform.get_drive_service
            aws_key_path (str): path to the AWS access key file: that is, the aws.csv file with public and private key
            qualification_type_name (str): human-readable name of the qualification to use to tag workers answering
            more than max_forms_per_worker forms.
            If the qualification_type_name be found in the existing qualifications i.e. it has never been used or used then deleted
            with the current account, this will create a new MTurk qualification type.
            qualification_description (str): description of qualification_type_name
            qualification_type_id (str): MTurk qualification type id. If set to a value, override the qualification
            type id designated by qualification_type_name.
            max_forms_per_worker (int): maximum number of forms a worker is allowed to complete in the pool
            production (Bool):  set to False in order to use the MTurk Sandbox, True otherwise
        """
        self.production = production
        # retrieval of the access keys
        aws_access_key_id, aws_secret_access_key = read_access_keys(aws_key_path)
        # creation of an self.client client
        self.client = create_mturk_client(
            aws_access_key_id, aws_secret_access_key, production
        )
        self.max_forms_per_worker = max_forms_per_worker
        self.form_results_dir = form_results_dir
        self.gform_map = gform_map
        self.drive_service = drive_service

        self.thread = None
        self.tagged_workers = set()
        existing_qualifs = self.client.list_qualification_types(
            MustBeRequestable=False, Query=qualification_type_name
        )["QualificationTypes"]
        if qualification_type_id is not None:
            self.qualification_type_id = qualification_type_id
        else:
            if len(existing_qualifs) > 0:
                assert len(existing_qualifs) == 1
                qualif = existing_qualifs[0]
                assert qualif["Name"] == qualification_type_name
                self.qualification_type_id = qualif["QualificationTypeId"]
            else:
                if len(qualification_description) == 0:
                    raise ValueError(
                        "Provide a non empty description when creating a qualification type"
                    )
                qualif = self.client.create_qualification_type(
                    Name=qualification_type_name,
                    Description=qualification_description,
                    QualificationTypeStatus="Active",
                    AutoGranted=True,
                    AutoGrantedValue=0,
                )
                self.qualification_type_id = qualif["QualificationType"][
                    "QualificationTypeId"
                ]

    def get_qualif_requirement(self):
        """
        Return the qualification requirement associated with the current watcher.

        Returns:
            [dict]: Qualification Requirement as in the boto3 nomenclature
        """
        return {
            "QualificationTypeId": self.qualification_type_id,
            "Comparator": "DoesNotExist",
            "ActionsGuarded": "DiscoverPreviewAndAccept",
        }

    def get_workers2tag(self):
        """
        Return the set of workerid that need to get tagged

        Returns:
            [set of str]: set of Worker Id that need to be tagged in order not to
            find any more forms from the pool in their MTurk searche
        """
        download_multi_csv(self.gform_map, self.form_results_dir, self.drive_service)
        meta_df = []
        for form_path in self.form_results_dir.iterdir():
            df = pd.read_csv(form_path, usecols=["WorkerID"])
            meta_df.append(df)
        meta_df = pd.concat(meta_df, axis=0)
        # number of different
        forms_count = meta_df["WorkerID"].value_counts()
        forms_count = forms_count[forms_count >= self.max_forms_per_worker]
        return set(forms_count.index.tolist())

    def get_tagged_workers(self):
        """
        Return the set of Workerid that are already tagged

        Returns:
            [set of str]: tagged workers ids
        """
        # search for workers already tagged
        tagged_workers = set()
        qualifs = self.client.list_workers_with_qualification_type(
            QualificationTypeId=self.qualification_type_id
        )
        for qualif in qualifs["Qualifications"]:
            if qualif["QualificationTypeId"] == self.qualification_type_id:
                tagged_workers.add(qualif["WorkerId"])
        return tagged_workers

    def monitor(self, sleep_time=10):
        """
        Function to run in detached thread: checks periodically for new workers to tag
        Downloads at each iteration the most recent version of the results for the current batch's
        forms.

        Args:
            sleep_time (int): time to sleep at each iteration
        """
        # search for workers already tagged
        i = 0
        while self.monitor:
            # information comes from google drive
            tagged_workers = self.get_tagged_workers()
            self.tagged_workers = tagged_workers

            workers2tag = self.get_workers2tag()
            # remove the workers already tagged
            workers2tag = workers2tag - tagged_workers

            for workerid in tagged_workers:
                print(f"{workerid},")

            for workerid in workers2tag:
                try:
                    self.client.associate_qualification_with_worker(
                        QualificationTypeId=self.qualification_type_id,
                        WorkerId=workerid,
                        IntegerValue=1,
                        SendNotification=False,
                    )
                except ClientError:
                    print(f"Non valid worker id {workerid}")
            i += 1

            for i in range(sleep_time):
                sleep(1)
                if not self.monitor:
                    return 0

    def start_monitor(
        self,
    ):
        """
        Detaches a thread executing the Watcher.monitor function if no thread is already running.
        """
        if self.thread is None:
            self.thread = threading.Thread(target=self.monitor, args=(), daemon=True)
            print(f"Starting {self.thread.name}")
            self.thread.start()
        else:
            print(f"{self.thread.name} already in use")

    def stop_monitor(
        self,
    ):
        """
        Stop the thread executing the Watcher.monitor function if such a thread is running.
        """
        if self.thread is not None:
            name = self.thread.name
            print(f"Stopping {name}..")
            self.monitor = False
            self.thread.join()
            print(f"{name} stopped.")
            self.thread = None
        else:
            print("No monitor to stop")

    def untag_all_workers(self):
        """
        Untag all workers tagged with the qualification type associated with the Watcher
        """
        workers = self.get_tagged_workers()
        for wid in workers:
            self.client.disassociate_qualification_from_worker(
                WorkerId=wid,
                QualificationTypeId=self.qualification_type_id,
                Reason="First pilot terminated, you can answer the next pilots",
            )
        print(f"All workers untagged! ({workers})")
