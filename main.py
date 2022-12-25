#!/usr/bin/env python3

import argparse
import concurrent.futures
import json
import logging
import queue
import os
import requests
import textwrap

from git import Repo
from requests.structures import CaseInsensitiveDict


def create_queue_from_text_file(file: str):
    values = queue.Queue()

    if os.path.isfile(file):
        with open(file, "r") as f:
            results = [line.rstrip() for line in f]

        for result in results:
            values.put(result)

        return values
    else:
        logging.error(f"Could not read values from {file}")
        raise SystemExit(1)


def get_pages(query_string: str):
    session = requests.Session()
    
    try:
        first_page = session.get(url=query_string, headers=HEADERS, params={'per_page': 100})
        first_page.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(e)
        raise SystemExit(1)
    
    yield first_page.json()
    number_of_pages = first_page.headers['X-Total-Pages']
    
    for page_number in range(2, int(number_of_pages)):
        next_page = session.get(query_string, params={'page': page_number, 'per_page': 100}).json()
        yield next_page


def get_subgroups(group_id: str):

    subgroup_ids = queue.Queue()
            
    for page in get_pages(query_string=f"https://gitlab.com/api/v4/groups/{group_id}/subgroups"):
        
        for value in page:
            subgroup_ids.put(value['id'])
        
            with open(GROUP_IDS_FILE, "a") as f:
                f.write(f"{value['id']}\n")

    return subgroup_ids


def enumerate_groups(group_ids: queue):

    if group_ids.empty():
        return
    else:
        with concurrent.futures.ThreadPoolExecutor() as pool:

            while not group_ids.empty():
                group_id = group_ids.get()
                future = pool.submit(get_subgroups, group_id)
                results = future.result()

        enumerate_groups(results)


def get_projects(group_id: str):
    for page in get_pages(query_string=f"https://gitlab.com/api/v4/groups/{group_id}/projects"):
        for value in page:
            with open(PROJECT_IDS_FILE, "a") as f:
                f.write(f"{value['id']}\n")


def enumerate_projects(group_ids: queue):

    with concurrent.futures.ThreadPoolExecutor() as pool:
        while not group_ids.empty():
            group_id = group_ids.get()
            pool.submit(get_projects, group_id)


def clone_project(project_id: str):
    project_info = f"https://gitlab.com/api/v4/projects/{project_id}"
    r = requests.get(project_info, headers=HEADERS)

    if r.status_code == 200:
        r_json = json.loads(r.text)

        if USE_SSH:
            Repo.clone_from(url=r_json["ssh_url_to_repo"], to_path=f"{OUTPUT_DIRECTORY}/{r_json['path_with_namespace']}", env=dict(GIT_SSH_CMD=GIT_SSH_CMD))
        else:
            Repo.clone_from(url=r_json["http_url_to_repo"], to_path=f"{OUTPUT_DIRECTORY}/{r_json['path_with_namespace']}")
    else:
        logging.error(f"Failed to query {project_info}, got {r.status_code}")


def clone_projects(project_ids: queue):
    with concurrent.futures.ThreadPoolExecutor() as pool:
        while not project_ids.empty():
            project_id = project_ids.get()
            logging.debug(f"Adding {project_id} job to thread pool")
            pool.submit(clone_project, project_id)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Gitlab Group and Project Scraper", formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog=textwrap.dedent(
                    '''Examples:
                        Examples to follow...
                    '''))

    parser.add_argument("-o", "--output-dir", help="The full path to the directory in which to store output.")
    parser.add_argument("-r", "--root-id", help="The ID of the Gitlab group/project at which to begin enumeration.")
    parser.add_argument("-b", "--bearer-token", help="The Gitlab Personal Access Token to use when making requests.")
    parser.add_argument("-l", "--log-level", help="Logging level: INFO, DEBUG")
    parser.add_argument("-s", "--use-ssh", action="store_true", help="Use SSH when cloning projects")
    parser.add_argument("-k", "--ssh-key", help="Path to the key file to use when cloning with SSH")

    args = parser.parse_args()

    format = "%(asctime)s: %(message)s"

    if args.log_level == "DEBUG":
        logging.basicConfig(format=format, level=logging.DEBUG, datefmt="%H:%M:%S")
    else:
        logging.basicConfig(format=format, level=logging.DEBUG, datefmt="%H:%M:%S")

    HEADERS = CaseInsensitiveDict()
    HEADERS["Accept"] = "application/json"
    HEADERS["Authorization"] = f"Bearer {args.bearer_token}"

    OUTPUT_DIRECTORY = args.output_dir
    GROUP_IDS_FILE = f"{OUTPUT_DIRECTORY}/group-ids.txt"
    PROJECT_IDS_FILE = f"{OUTPUT_DIRECTORY}/project-ids.txt"

    if args.use_ssh:
        USE_SSH = args.use_ssh
        GIT_SSH_KEY = args.ssh_key
        GIT_SSH_CMD = f"ssh -i {GIT_SSH_KEY}"

    with open(GROUP_IDS_FILE, "a") as f:
        f.write(f"{args.root_id}\n")

    starting_group_queue = queue.Queue()
    starting_group_queue.put(args.root_id)

    enumerate_groups(starting_group_queue)
    enumerate_projects(create_queue_from_text_file(GROUP_IDS_FILE))
    clone_projects(create_queue_from_text_file(PROJECT_IDS_FILE))
