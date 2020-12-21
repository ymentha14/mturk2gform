""" misc utilities functions"""
from pathlib import Path
import pandas as pd

def read_access_keys(file_path):
    """
    Read the AWS keys at the given file_path

    Args:
        file_path (str): path to the AWS access key file

    Return
        [str],[str]: the access key and the secret access key
    """
    keys_df = pd.read_csv(file_path,header=None)
    assert(keys_df.shape == (2,1) or keys_df.shape == (1,2))
    aws_access_key_id = keys_df.loc[0][0]
    aws_secret_access_key = keys_df.loc[1][0]  if keys_df.shape == (2,1) else  keys_df.loc[1][0]
    return aws_access_key_id,aws_secret_access_key
