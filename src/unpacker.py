import os
from reader import AIPKReader


def extract_all(aipk_path, output_dir, verify=False):
    reader = AIPKReader(aipk_path, verify=verify)

    try:
        os.makedirs(output_dir, exist_ok=True)
        reader.extract_all(output_dir)
    finally:
        reader.close()


def extract_one(aipk_path, target_path, output_path, verify=False):
    reader = AIPKReader(aipk_path, verify=verify)

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        reader.extract_one(target_path, output_path)
    finally:
        reader.close()


def list_files(aipk_path):
    reader = AIPKReader(aipk_path, verify=False)

    try:
        return reader.list()
    finally:
        reader.close()


def get_info(aipk_path):
    reader = AIPKReader(aipk_path, verify=False)

    try:
        return reader.info()
    finally:
        reader.close()