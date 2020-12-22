import io
import os
import pickle as pk
import shutil
from pathlib import Path
from pdb import set_trace

import pandas as pd
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def get_drive_service(creds_dir):
    """
    Return the drive service for files downloading.
    Inspired from https://developers.google.com/people/quickstart/python

    Args:
        creds_dir (pathlib.Path): path to directory containing the credentials.json.
        Instructions to obtain such a file are available here https://developers.google.com/people/quickstart/python/

    Returns:
        [googleapiclient.discovery.Resource]: service object to Google Drive
    """
    # directory cleaning
    creds_dir = Path(creds_dir) if type(creds_dir) == str else creds_dir
    token_path = creds_dir.joinpath("token.pk")
    creds_path = creds_dir.joinpath("credentials.json")

    # If modifying these scopes, delete the file token.pickle.
    scopes = ["https://www.googleapis.com/auth/drive"]
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pk.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "wb") as token:
            pk.dump(creds, token)

    service = build("drive", "v3", credentials=creds)
    return service


def download_drive_txt(gform_map_path, gform_map_id, service):
    """
    Download the gform_map file to the provided path

    Args:
        gform_map_path (str): path where to store a local version of the gform_map
        gform_map_id (str): gdrive id of the gform_map
        service (gdrive service): as returned by get_drive_service
    """

    request = service.files().export(fileId=gform_map_id, mimeType="text/plain")

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print("Download %d%%" % int(status.progress() * 100))

    # The file has been downloaded into RAM, now save it in a file
    fh.seek(0)
    with open(gform_map_path, "wb") as f:
        shutil.copyfileobj(fh, f, length=131072)


def get_gform_map(service, gform_map_id, gform_map_path):
    """
    Return the gform_map,i.e. a dictionary mapping to each form index the url to the corresponding
    form ('url' key) and the drive id pointing to the spreadsheet containing the results of this form
    ('driveid' key).

    Args:
        service (googleapiclient.discovery.Resource): as returned by get_drive_service
        gform_map_id (str): drive_id of the gform_map file. This file must respect the following structure:
        <form index>,<url to form>,<url to form spreadsheet>
        gform_map_path (str): path where to store a local version of the gform_map.txt file

    Returns:
        [dict]: dictionary mapping to each form index the url to the corresponding
        form ('url' key) and the drive id pointing to the spreadsheet containing the results of this form
        ('driveid' key).
    """
    download_drive_txt(
        gform_map_path, gform_map_id, service
    )  # download the most recent url_index
    gform_map = pd.read_csv(
        gform_map_path, sep=",", header=None, names=["url", "driveid"]
    )
    gform_map["driveid"] = gform_map["driveid"].apply(lambda x: x.split("/")[-2])
    gform_map = gform_map.to_dict(orient="index")
    return gform_map


def get_batch_gform_map(service, file_id, gform_map_path, form_indexes):
    """
    Used in case of batched dataset gathering.
    Returns the subpart of gform_map specific to the form_indexes passed in parameter

    Args:
        service (googleapiclient.discovery.Resource): as returned by get_drive_service
        gform_map_id (str): drive_id of the gform_map file. This file must respect the following structure:
        <form index>,<url to form>,<url to form spreadsheet>
        gform_map_path (str): path where to store a local version of the gform_map.txt file
        form_indexes (list of int): indexes of the forms for the current batch
    """
    gform_map = get_gform_map(service, file_id, gform_map_path)
    # we limit the forms we want to treat to the one of the batch
    gform_map_batch = {
        key: value for key, value in gform_map.items() if key in form_indexes
    }
    return gform_map_batch


def download_csv(csv_path, fileId, service, verbose=False):
    """
    Download the spreadsheet result of a form as a csv file

    Args:
        csv_path(str): path where to store a local .csv version of the spreadsheet
        fileId (str): drive id of the spreadsheet
        service (googleapiclient.discovery.Resource]): as returned by get_drive_service
    """

    data = service.files().export(fileId=fileId, mimeType="text/csv").execute()

    # if non-empty file
    if data:
        with open(csv_path, "wb") as f:
            f.write(data)
        if verbose:
            print(f"Download 100% {csv_path}")
    else:
        raise ValueError("Empty file")


def download_multi_csv(gform_map, result_dir, service):
    """
    Iterate over the forms present in the gform_map and sequentially calls download_csv
    on, downloading their respective most recent version

    Args:
        gform_map (dict): dictionary mapping to each form index the url to the corresponding
        form ('url' key) and the drive id pointing to the spreadsheet containing the results of this form
        ('driveid' key).
        result_dir (str): directory where to download the results.
        service (googleapiclient.discovery.Resource]): as returned by get_drive_service
    """
    result_dir = Path(result_dir)
    for idx, driveid in [(idx, val["driveid"]) for idx, val in gform_map.items()]:
        path = result_dir.joinpath(f"{idx}.csv")
        download_csv(path, driveid, service)
