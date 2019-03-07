#!/usr/bin/env python

import argparse
import json
import os
import re
import subprocess
import sys


root = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 os.pardir,
                 os.pardir))


def run(cmd, return_stdout=False, **kwargs):
    print(" ".join(cmd))
    if return_stdout:
        f = subprocess.check_output
    else:
        f = subprocess.check_call
    return f(cmd, **kwargs)


def get_parser():
    p = argparse.ArgumentParser()
    p.add_argument("job",
                   help="Name of the job associated with the current event")
    p.add_argument("script", help="Script to run for the job")
    return p


def get_extra_jobs(event):
    body = None
    jobs = set()
    if "commits" in event:
        body = event["commits"][0]["message"]
    elif "pull_request" in event:
        body = event["pull_request"]["body"]

    if not body:
        return jobs

    regexp = re.compile("\s*tc-jobs:(.*)$")

    for line in body.splitlines():
        m = regexp.match(line)
        if m:
            items = m.group(1)
            for item in items.split(","):
                jobs.add(item.strip())
            break
    return jobs


def set_variables(event):
    # Set some variables that we use to get the commits on the current branch
    ref_prefix = "refs/heads/"
    pull_request = "false"
    if "pull_request" in event:
        pull_request = str(event["pull_request"]["number"])
        # Note that this is the branch that a PR will merge to,
        # not the branch name for the PR
        branch = event["pull_request"]["base"]["ref"]
    elif "ref" in event:
        branch = event["ref"]
        if branch.startswith(ref_prefix):
            branch = branch[len(ref_prefix):]

    os.environ.update({"GITHUB_PULL_REQUEST": pull_request,
                       "GITHUB_BRANCH": branch})


def include_job(job):
    jobs_str = run([os.path.join(root, "wpt"),
                    "test-jobs"], return_stdout=True)
    print(jobs_str)
    return job in set(jobs_str.splitlines())


def main():
    args = get_parser().parse_args()
    event = json.loads(os.environ["TASK_EVENT"])

    set_variables(event)

    if os.environ.get("GITHUB_BRANCH"):
        # Ensure that the remote base branch exists
        # TODO: move this somewhere earlier in the task
        run(["git", "fetch", "origin", "%s:%s" % (os.environ["GITHUB_BRANCH"],
                                                  os.environ["GITHUB_BRANCH"])])

    extra_jobs = get_extra_jobs(event)

    job = args.job

    run_if = [(lambda: job == "all", "job set to 'all'"),
              (lambda:"all" in extra_jobs, "Manually specified jobs includes 'all'"),
              (lambda:job in extra_jobs, "Manually specified jobs includes '%s'" % job),
              (lambda:include_job(job), "CI required jobs includes '%s'" % job)]

    for fn, msg in run_if:
        if fn():
            print(msg)
            # Run the job
            os.chdir(root)
            print(args.script)
            sys.exit(subprocess.call([args.script]))
            break
    else:
        print("Job not scheduled for this push")


if __name__ == "__main__":
    main()
