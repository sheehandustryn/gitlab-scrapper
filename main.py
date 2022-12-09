#!/usr/bin/env python3

import argparse
from git import Repo
import json
import logging
import queue
import os
import requests
from requests.structures import CaseInsensitiveDict
import textwrap
import threading

def create_queue(values: str, output_directory: str):
  logging.info("Generating initial in memory list of IDs...")
  results = queue.Queue()

  if os.path.isfile(values):
    logging.info("Processing as file path...")
    if os.path.exists(values):

      with open(values, "r") as f:
        ids = f.readlines()

        for id in ids:

          results.put(id)
    else:
      "Provided path for file containing Gitlab group IDs does not exist."
  else:
    logging.info("Processing as single id...")
    with open(f"{output_directory}/group-ids.txt", "a") as f:
      f.write(f"{values}\n")
    results.put(values)

  return results

def clone_project(project_id: str, output_directory: str, headers: CaseInsensitiveDict):
  project_info = f"https://gitlab.com/api/v4/projects/{project_id}"
  r = requests.get(project_info, headers=headers)

  if r.status_code == 200:
    r_json  = json.loads(r.text)
    logging.info(f"Cloning into {output_directory}/{r_json['path_with_namespace']}...")
    Repo.clone_from(url=r_json["http_url_to_repo"], to_path=f"{output_directory}/{r_json['path_with_namespace']}")
  else:
    logging.info(f"Unable to query project info at {project_info}, got: {r.status_code}")

def enumerate_groups(group_ids: queue, output_directory: str, headers: CaseInsensitiveDict):
  logging.info("Enumerating groups...")

  with open(f"{output_directory}/group-ids.txt", "a") as f:

    while not group_ids.empty():
      group_id = group_ids.get()
      subgroups = f" https://gitlab.com/api/v4/groups/{group_id}/subgroups?per_page=100"
      r = requests.get(subgroups, headers=headers)

      if r.status_code == 200:
        r_json = json.loads(r.text)

        for group in r_json:
          group_ids.put(group["id"])
          f.write(f"{group['id']}\n")

def enumerate_projects(group_ids: queue, output_directory: str, headers: CaseInsensitiveDict):
  logging.info("Enumerating projects...")

  with open(f"{output_directory}/project-ids.txt", "a") as f:

    while not group_ids.empty():
      group_id = group_ids.get()
      projects = f"https://gitlab.com/api/v4/groups/{group_id}/projects?per_page=100"
      r = requests.get(projects, headers=headers)

      if r.status_code == 200:
        r_json = json.loads(r.text)

        for project in r_json:
          f.write(f"{project['id']}\n")

def clone_projects(project_ids: queue, output_directory: str, threads: int, headers: CaseInsensitiveDict):
  logging.info("Cloning projects...")

  while not project_ids.empty():
    cloner_threads = list()

    for i in range(threads):
      try:
        project_id = project_ids.get()
      except:
        break

      t = threading.Thread(target=clone_project(project_id=project_id, output_directory=output_directory, headers=headers))
      cloner_threads.append(t)
      t.start()

    for cloner_thread in cloner_threads:
      cloner_thread.join()

if __name__ == '__main__':

  format = "%(asctime)s: %(message)s"
  logging.basicConfig(format=format, level=logging.INFO, datefmt="%H:%M:%S")

  parser = argparse.ArgumentParser(
    description="Gitlab Group and Project Scraper",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog=textwrap.dedent('''Examples:
      Examples to follow...
    '''))

  parser.add_argument("-g", "--groups-file", help="Full path to a file containing a list of Gitlab group IDs in json format.")
  parser.add_argument("-o", "--output-dir", help="The full path to the directory in which to store output.")
  parser.add_argument("-p", "--projects-list", help="Full path to a file containing a list of Gitlab project IDs")
  parser.add_argument("-r", "--root-group-id", help="The ID of the Gitlab group for which to enumerate all subgroups. Required if --enumerate-groups is used.")
  parser.add_argument("-b", "--bearer-token", help="The Gitlab Personal Access Token to use when making requests.")
  parser.add_argument("-t", "--threads", help="Specify the number of threads to use for cloning projects.")

  parser.add_argument("-G", "--enumerate-groups", action="store_true", help="Enumerate all subgroups of the specified Gitlab group(s). Use either --group-id or --groups-list with this option.")
  parser.add_argument("-P", "--enumerate-projects", action="store_true", help="Enumerate all Gitlab projects found under each group discovered or provided.")
  parser.add_argument("-C", "--clone-projects", action="store_true", help="Clone all Gitlab projects. If used either --enumerate-projects or --projects-list must be provided.")

  args = parser.parse_args()

  HEADERS = CaseInsensitiveDict()
  HEADERS["Accept"] = "application/json"
  HEADERS["Authorization"] = f"Bearer {args.bearer_token}"

  if args.enumerate_groups and args.enumerate_projects and args.clone_projects:

    if args.root_group_id:
      enumerate_groups(group_ids=create_queue(args.root_group_id, output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)
    elif args.groups_list:
        enumerate_groups(group_ids=create_queue(args.groups_file, output_dir=args.output_dir), output_directory=args.output_dir, headers=HEADERS)

    enumerate_projects(group_ids=create_queue(f"{args.output_dir}/group-ids.txt", output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)
    clone_projects(project_ids=create_queue(f"{args.output_dir}/project-ids.txt", output_directory=args.output_dir), output_directory=args.output_dir, threads=int(args.threads),headers=HEADERS)

  elif args.enumerate_groups and args.enumerate_projects:

    if args.root_group_id:
      enumerate_groups(group_ids=create_queue(args.root_group_id, output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)
    elif args.groups_list:
        enumerate_groups(group_ids=create_queue(args.groups_file, output_dir=args.output_dir), output_directory=args.output_dir, headers=HEADERS)

    enumerate_projects(group_ids=create_queue(f"{args.output_dir}/group-ids.txt", output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)

  elif args.enumerate_groups:
    if args.root_group_id:
      enumerate_groups(group_ids=create_queue(args.root_group_id, output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)
    elif args.groups_list:
        enumerate_groups(group_ids=create_queue(args.groups_file, output_dir=args.output_dir), output_directory=args.output_dir, headers=HEADERS)

  else:
    if args.root_group_id:
      enumerate_projects(group_ids=create_queue(args.root_group_id, output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)
    elif args.groups_list:
        enumerate_projects(group_ids=create_queue(args.groups_list, output_directory=args.output_dir), output_directory=args.output_dir, headers=HEADERS)
