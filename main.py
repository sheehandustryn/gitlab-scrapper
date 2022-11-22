#!/usr/bin/env python3

import argparse
import concurrent.futures
import gitlab
import logging
import textwrap

from git import Repo


def get_subgroups(group):
    for subgroup in group.subgroups.list(iterator=True, all_available=True):
        with open(GROUP_IDS_FILE, "a") as f:
            f.write(f"{str(subgroup.attributes['id'])}\n")

        with open(GROUP_NAMES_FILE, "a") as f:
            f.write(f"{str(subgroup.attributes['full_path'])}\n")


def get_descendant_groups(group):
    for subgroup in group.descendant_groups.list(iterator=True, all_available=True):
        with open(GROUP_IDS_FILE, "a") as f:
            f.write(f"{str(subgroup.attributes['id'])}\n")

        with open(GROUP_NAMES_FILE, "a") as f:
            f.write(f"{str(subgroup.attributes['full_path'])}\n")


def generate_full_paths_list():
    with open(GROUP_NAMES_FILE, "r") as r:
        generator = (line.rstrip() for line in r)
        full_paths = []
        for item in generator:
            full_paths.append(item)
            
        return full_paths

def get_subgroups_by_full_path(group):

        logging.info("List being checked against...")
        logging.info(FULL_PATHS)

        for subgroup in group.subgroups.list(iterator=True, all_available=True):
            logging.info(f"Checking {subgroup.attributes['full_path']}")
            if subgroup.attributes['full_path'] in FULL_PATHS:
                with open(GROUP_IDS_FILE, "a") as f:
                    f.write(f"{str(subgroup.attributes['id'])}\n")


def get_descendant_groups_by_full_path(group):
        for subgroup in group.descendant_groups.list(iterator=True, all_available=True):
            logging.info(f"Checking {subgroup.attributes['full_path']}")
            if subgroup.attributes['full_path'] in FULL_PATHS:
                with open(GROUP_IDS_FILE, "a") as f:
                    f.write(f"{str(subgroup.attributes['id'])}\n")


def get_groups_by_full_path():

    groups = GL.groups.get(ROOT_ID)
    with open(GROUP_NAMES_FILE, "r") as r:
        full_paths = (line.rstrip() for line in r)

        for group in groups:
            if group.attributes['full_path'] in full_paths:
                with open(GROUP_IDS_FILE, "a") as f:
                    f.write(f"{str(group.attributes['id'])}\n")


def enumerate_groups():

    try:
        first_page = session.get(url=query_string, headers=HEADERS, params={'per_page': 100, 'all_available': 'true'})
        first_page.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(e)
        raise SystemExit(1)

    yield first_page
    number_of_pages = first_page.headers['X-Total-Pages']

    for page_number in range(2, int(number_of_pages)):
        next_page = session.get(query_string, params={'page': page_number, 'per_page': 100, 'all_available': 'true'})
        yield next_page


def get_groups(group_id: str):

    group_ids = queue.Queue()

    for page in get_pages(query_string=f"https://gitlab.com/api/v4/groups/{group_id}/subgroups"):
        response_json = json.loads(page.text)
        for value in response_json:
            if type(value) is dict:
                group_ids.put(value['id'])

                with open(GROUP_IDS_FILE, "a") as f:
                    f.write(f"{value['id']}\n")
            else:
                logging.info(f"Value was of type: {type(value)}")
                logging.info("Contents:")
                logging.info(value)

    for page in get_pages(query_string=f"https://gitlab.com/api/v4/groups/{group_id}/descendant_groups"):
        response_json = json.loads(page.text)
        for value in response_json:
            if type(value) is dict:
                group_ids.put(value['id'])

                with open(GROUP_IDS_FILE, "a") as f:
                    f.write(f"{value['id']}\n")
            else:
                logging.info(f"Value was of type: {type(value)}")
                logging.info("Contents:")
                logging.info(value)

    return group_ids


def enumerate_groups(group_ids: queue):

    if group_ids.empty():
        return
    else:
        with concurrent.futures.ThreadPoolExecutor() as pool:

            while not group_ids.empty():
                group_id = group_ids.get()
                future = pool.submit(get_groups, group_id)
                results = future.result()

        enumerate_groups(results)


def get_projects(group_id: str):
    for page in get_pages(query_string=f"https://gitlab.com/api/v4/groups/{group_id}/projects"):
        response_json = json.loads(page.text)
        for value in response_json:
            if type(value) is dict:
                with open(PROJECT_IDS_FILE, "a") as f:
                    f.write(f"{value['id']}\n")
            else:
                logging.info(f"Value was of type: {type(value)}")
                logging.info("Contents:")
                logging.info(value)


def enumerate_projects(group_ids: queue):

    with concurrent.futures.ThreadPoolExecutor() as pool:
        if CHECK_FULL_PATHS:
            pool.submit(get_subgroups_by_full_path, group)
            pool.submit(get_descendant_groups_by_full_path, group)
        else:
            pool.submit(get_subgroups, group)
            pool.submit(get_descendant_groups, group)


def get_projects(group):
    for project in group.projects.list(iterator=True):
        with open(PROJECT_IDS_FILE, "a") as f:
            f.write(f"{str(project.attributes['id'])}\n")

        with open(PROJECT_NAMES_FILE, "a") as f:
            f.write(f"{str(project.attributes['path_with_namespace'])}\n")


def enumerate_projects():

    with open(GROUP_IDS_FILE, "r") as r:
        results = (line.rstrip() for line in r)

        with concurrent.futures.ThreadPoolExecutor() as pool:
            for result in results:
                group = GL.groups.get(result)
                pool.submit(get_projects, group)


def clone_project(project_id: str):
    project = GL.projects.get(project_id)

    if USE_SSH:
        url = project.attributes['ssh_url_to_repo']
        path = project.attributes['path_with_namespace']
        Repo.clone_from(url=url, to_path=f"{OUTPUT_DIRECTORY}/{path}", env=dict(GIT_SSH_CMD=GIT_SSH_CMD))
    else:
        url = project.attributes['http_url_to_repo']
        path = project.attributes['path_with_namespace']
        Repo.clone_from(url=url, to_path=f"{OUTPUT_DIRECTORY}/{path}")


def clone_projects():
    with open(PROJECT_IDS_FILE, "r") as r:
        projects = (line.rstrip() for line in r)

        with concurrent.futures.ThreadPoolExecutor() as pool:
            for project in projects:
                pool.submit(clone_project, project)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Gitlab Group and Project Scraper", formatter_class=argparse.RawDescriptionHelpFormatter,
                epilog=textwrap.dedent(
                    '''Examples:
                        Examples to follow...
                    '''))

    parser.add_argument("-r", "--root-id", help="The ID of the Gitlab group/project at which to begin enumeration.")
    parser.add_argument("-o", "--output-dir", help="The full path to the directory in which to store output.")
    parser.add_argument("-b", "--bearer-token", help="The Gitlab Personal Access Token to use when making requests.")
    parser.add_argument("-l", "--log-level", help="Logging level: INFO, DEBUG")
    parser.add_argument("-s", "--use-ssh", action="store_true", help="Use SSH when cloning projects")
    parser.add_argument("-k", "--ssh-key", help="Path to the key file to use when cloning with SSH")
    parser.add_argument("-f", "--check-full-paths", action="store_true", help="Use if you have a list of paths to groups for which you need to retrieve the IDs")

    args = parser.parse_args()

    format = "%(asctime)s: %(message)s"

    match args.log_level:
        case "DEBUG":
            logging.basicConfig(format=format, level=logging.DEBUG, datefmt="%H:%M:%S")
        case "ERROR":
            logging.basicConfig(format=format, level=logging.ERROR, datefmt="%H:%M:%S")
        case "FATAL":
            logging.basicConfig(format=format, level=logging.FATAL, datefmt="%H:%M:%S")
        case "INFO":
            logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")
        case "WARN":
            logging.basicConfig(format=format, level=logging.WARN, datefmt="%H:%M:%S")
        case _:
            logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")

    OUTPUT_DIRECTORY = args.output_dir
    OUTPUT_DIRECTORY = args.output_dir
    CHECK_FULL_PATHS = args.check_full_paths
    GROUP_IDS_FILE = f"{OUTPUT_DIRECTORY}/group-ids.txt"
    GROUP_NAMES_FILE = f"{OUTPUT_DIRECTORY}/group-names.txt"
    PROJECT_IDS_FILE = f"{OUTPUT_DIRECTORY}/project-ids.txt"
    PROJECT_NAMES_FILE = f"{OUTPUT_DIRECTORY}/project-names.txt"
    PERSONAL_TOKEN = args.bearer_token
    ROOT_ID = args.root_id

    if args.use_ssh:
        USE_SSH = args.use_ssh
        GIT_SSH_KEY = args.ssh_key
        GIT_SSH_CMD = f"ssh -i {GIT_SSH_KEY}"

    GL = gitlab.Gitlab(private_token=f"{PERSONAL_TOKEN}")

    if CHECK_FULL_PATHS:
        FULL_PATHS = generate_full_paths_list()
        enumerate_groups()
        enumerate_projects()
        clone_projects()
    else:
        enumerate_groups()
        enumerate_projects()
        clone_projects()
