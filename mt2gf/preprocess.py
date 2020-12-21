"""
Preprocessing functions before mturk data gathering
"""
import pandas as pd
import resource
from copy import copy
from mt2gf.gform import download_drive_txt
from pathlib import Path


def create_batch_directories(directory, n_dirs):
    """
    create the directories to receive the results from the batches

    Args:
        directory (pathlib.Path): directory in which create the batches directories
        n_dirs (int): number of directories to create
    """
    for n in range(n_dirs):
        directory.joinpath(str(n)).mkdir(parents=True, exist_ok=True)


def batchnumber2formidxes(batch_number, batch_size):
    """
    Convert a batch number to its respective form indexes

    Args:
        batch_number (int): index of the batch
        batch_size (int): size of the batch
    """
    start_idx = batch_number * batch_size
    forms_idxes = list(range(start_idx, start_idx + batch_size))
    return forms_idxes


def check_previous_batches(recent_batch_number, parent_dir, MaxAssignments, batch_size):
    """
    Check the number of files and their size in all previous batches up to
    current batch

    Args:
        recent_bach_number (int): most recent batch (not included)
        parent_dir (pathlib.Path): parent directory in containing the batches
        MaxAssignments (int): total number of worker answer expected per form
        batch_size (int): number of forms to get ansewred per batch
    """
    # we check up to the most recent batch
    for batch_number in range(recent_batch_number):
        batch_path = parent_dir.joinpath(str(batch_number))
        valid, msg = check_is_complete(batch_path, MaxAssignments, batch_size)
        if not valid:
            raise ValueError(msg)
    print(f"All batches clean up to batch {recent_batch_number}")


def check_is_complete(batch_path, MaxAssignments, batch_size):
    """
    check that the batch present at batch_path follows some structure:
    i.e. has batch_size files and each file has at least MaxAssignments rows.

    Args:
        batch_path (str): path where to store the results of the batch
        MaxAssignments (int): total number of worker answer expected per form
        batch_size (int): number of forms to get ansewred per batch
    """
    batch_path = Path(batch_path)
    # form indexes we expect in this batch
    batch_number = int(batch_path.stem)

    form_idxes = batchnumber2formidxes(batch_number, batch_size)
    # extract the paths to the form files
    form_paths = [path for path in batch_path.glob("[0-9]*.csv")]

    # check for expected number of files
    if len(form_paths) != batch_size:
        raise ValueError(
            f"Problem of downloading: unexpected number of csv files in batch {batch_number}"
        )

    for form_path in form_paths:
        form_idx = form_path.stem

        # check the files are at the correct place
        if int(form_idx) not in form_idxes:
            raise ValueError(
                f"Form index {form_idx} should not be present in batch {batch_number}"
            )
        df = pd.read_csv(form_path)
        # check the files have the correct number of row
        if df.shape[0] < MaxAssignments:
            return (
                False,
                f"Form {form_idx} in batch {batch_number} is missing some entries.",
            )
    return True, ""


def get_batch_indexes(parent_dir, batch_number=None, batch_size=7, MaxAssignments=30):
    """
    Function to get the next batch information

    Args:
        batch_size(int): number of forms per batch
        batch_number(int): number of the batch to get indexes for

    Return:
        [pathlib.Path]: directory where to store the results of the batch
        [int]: index of the batch
        [list of int]: indexes of the forms to run the analysis for
    """
    if batch_number is None:
        batch_paths = [path.parent for path in parent_dir.glob("**/[0-9]*.csv")]
        if len(batch_paths) == 0:
            batch_number = 0
        else:
            recent_batch_dir = max(batch_paths, key=lambda x: x.stem)
            recent_batch_number = int(recent_batch_dir.stem)
            check_previous_batches(
                recent_batch_number, parent_dir, MaxAssignments, batch_size
            )

            complete, _ = check_is_complete(
                recent_batch_dir, MaxAssignments, batch_size
            )
            if complete:
                batch_number = recent_batch_number + 1
            else:
                print("Resuming previous incomplete batch")
                batch_number = recent_batch_number
    form_idxes = batchnumber2formidxes(batch_number, batch_size)
    batch_dir = parent_dir.joinpath(str(batch_number))
    return batch_dir, batch_number, form_idxes
