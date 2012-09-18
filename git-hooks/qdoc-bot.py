#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2012 Nokia Corporation and/or its subsidiary(-ies).
# Contact: http://www.qt-project.org/
#
# You may use this file under the terms of the 3-clause BSD license.
# See the file LICENSE from this package for details.
#

# Checkouts have to have the remote: origin codereview-bot:qt/qtbase.git

# Run with --dir and --addr
# python qdoc-bot.py --dir /home/USER/dev/qt-qdoc/ --addr codereview-bot
# --dir is where the sources are checked out
# --addr codereview-bot
# With .ssh/config:
# Host codereview-bot
#    Hostname codereview.qt-project.org
#    Port 29418
#    User qt_docbot
#    IdentityFile /home/USER/.ssh/docbot_id_rsa



import os
import subprocess
import sys
import logging

config = None # configuration object, it is initialized in main and passed to every worker process created by multiprocessing.Pool

#{
    #"change": {
        #"branch": "2.6",
        #"id": "I765c9e165f9e7a5e0928401f5c5254397ad9be0b",
        #"number": "33424",
        #"owner": {
            #"email": "Friedemann.Kleint@nokia.com",
            #"name": "Friedemann Kleint"
        #},
        #"project": "qt-creator/qt-creator",
        #"subject": "WIP: CDB: Fix some dumpers.",
        #"url": "https://codereview.qt-project.org/33424"
        #},
    #"patchSet": {
        #"number": "1",
        #"ref": "refs/changes/24/33424/1",
        #"revision": "c4dd516729ff8f9b7cb1e13d9c8f09560cf2c078",
        #"uploader": {
            #"email": "Friedemann.Kleint@nokia.com",
            #"name": "Friedemann Kleint"
        #}
    #},
    #"type": "patchset-created",
    #"uploader": {
        #"email": "Friedemann.Kleint@nokia.com",
        #"name": "Friedemann Kleint"
    #}
#}




#make sub-qdoc in src/tools
def run_qdoc(module_name):
    output = []
    try:
        environment = os.environ
        environment["CCACHE_BASEDIR"] =  os.getcwd()
        environment["QT_HASH_SEED"] = "1234"
        cmd = "(./configure -opensource -confirm-license -release && make sub-src-qmake_all && cd src/tools && make sub-qdoc) > /dev/null"
        subprocess.call(cmd, shell=True, env=environment)
        cmd = "make docs".split()
        output.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment).communicate()[1])
        def smart_concatenate(r, x):
            # concatenate multi-line comments
            if x.startswith("    ["):
                r[-1] = r[-1] + x  # add comment
            else:
                r.append(x)        # new error
            return r
        output[-1] = reduce(smart_concatenate, output[-1].split('\n'), [])
        output[-1].sort()
        output[-1] = "\n".join(output[-1])
    except KeyError:
        pass
    return "\n".join(output)

#ssh codereview.qt-project.org gerrit review --project qt/qtbase --message "hello" 33219,44
def post_review(event, message, score):
    project = event["change"]["project"]
    sha1 = event["patchSet"]["revision"]
    command = ["ssh", config.gerrit_address, "gerrit", "review", "--project", project, "--code-review", str(score)]
    if len(message) > 0:
        command += "--message", "\"" + message + "\"",
    command += sha1,
    logging.debug(command)
    if not config.sandbox:
        subprocess.check_call(command)
    elif event["change"]["number"] == '33219' or event["change"]["number"] == '33224':
        subprocess.check_call(command)

def remove_moved_doc_errors(fixes, errors):
    for fix in fixes:
        pos = fix.find(":")
        if pos >= 0:
            begin = "+" + fix[1:pos]
            end = fix[fix.find(":", pos+1):]
            logging.debug(end)
            for i in range(len(errors)):
                if errors[i].startswith(begin) and errors[i].endswith(end):
                    del errors[i]
                    break;
    message = ""
    for line in errors:
        message += line + "\n "
    return message

def review_output(event, output_no_patch, output_with_patch):
    try:
        import difflib
        project = event["change"]["project"]
        patch_set = event["patchSet"]
        url = event["change"]["url"]
        subject = event["change"]["subject"]
        new_error_count = output_with_patch.count("\n") - output_no_patch.count("\n")
        if new_error_count == 0:
            logging.info("NO DOC ERRORS: %s, %s", subject, url)
            #post_review(event, "", 1)
            return 0
        logging.debug("DIFF for %s: %s", subject, url)
        message = ""
        score = 0
        if new_error_count == 1:
            message += "This change introduces one new documentation error."
            score = -1
        elif new_error_count > 1:
            message += "This change introduces " + str(new_error_count) + " new documentation errors."
            score = -1
        elif new_error_count == -1:
            message += "This change removes a documentation error. Thank you!"
            score = 1
        else:
            message = "This change removes " + str(abs(new_error_count)) + " documentation errors. Thank you!"
            score = 1

        message += "\n\n "
        fixes = []
        errors = []
        line_count = 0
        for line in difflib.unified_diff(output_no_patch.split('\n'), output_with_patch.split('\n'), fromfile='before', tofile='after', n=0):
            line_count += 1
            if line_count > 2:
                if line[0] == "-":
                    fixes.append(line)
                elif line[0] == "+":
                    errors.append(line)
        new_errors = remove_moved_doc_errors(fixes, errors)
        if len(new_errors) > 0:
            message += "New qdoc warnings:\n \n "
            message += new_errors
        message += "\n\nThis comment was generated by the qtdoc bot.\n\nPlease contact Jedrzej Nowacki (nierob) or Frederik Gladhorn (fregl) if you have questions or think the script gives you false positives."
        logging.debug("Review result: %s", message)
        post_review(event, message, score)
        return score
    except:
        logging.error("Unexpected error: %s", sys.exc_info())


def fetch_change(project, patch_set, change_number):
    try:
        gerrit_url = config.gerrit_address + ":" + project
        # the mainlines need to be updated, so that we keep the updated refs and fetches don't start from scratch every time
        mainlines = subprocess.check_output(["git", "config", "remote.origin.fetch"]).rstrip()
        fetch_cmd = ["git", "fetch", "-f", "origin", patch_set["ref"]+":refs/changes/"+change_number, mainlines]
        num_tries = 0
        while True:
            try:
                p = subprocess.check_call(fetch_cmd)
                return 0

            except subprocess.CalledProcessError, e:
                # Try to fetch again - one problem is that running git fetch will fail if run simultaneously
                num_tries += 1
                logging.warn("Fetching subprocess failed, trying again: %s", e)
                import time
                time.sleep(30)
                if num_tries > 11:
                    raise e

    except subprocess.CalledProcessError, e:
        logging.error("Fetching subprocess failed too many times: %s", e)
        return -1


#git fetch https://codereview.qt-project.org/p/qt/qtbase refs/changes/46/32446/6 && git checkout FETCH_HEAD
def process_event(event_string):
    # load the event data
    import time
    start_time = time.time()
    import json
    import tempfile
    import shutil

    try:
        event = json.loads(event_string)
    except ValueError, e:
        logging.error("JSON loading problem: %s\nJSON data: %s", e, event_string)
        return -1

    if event["type"] != "patchset-created":
        return 0

    # go to the right project checkout
    project = event["change"]["project"]
    patch_set = event["patchSet"]
    change_number = event["change"]["number"]

    module_name = project.split('/')[-1]
    if module_name != "qtbase": # TODO for now we care only about qtbase
        logging.info("IGNORED MODULE: %s %s", module_name, patch_set)
        return 0

    logging.info("MODULE NAME: %s %s", module_name, patch_set)

    source_path = config.watcher_working_dir + "/" + project
    try:
        os.chdir(source_path)
    except OSError, e:
        logging.error("Unknown project, TODO write code to initialize it, error message: %s", e) #TODO for know you need to have qt/qtbase checkout ready
        logging.debug("Current dir was: %s", os.getcwd())
        return -1

    if fetch_change(project, patch_set, change_number) != 0:
        return -1

    try:
        #make own copy
        tmp_dir = tempfile.mkdtemp(prefix="qdoc_")
        logging.info("CREATING TMP DIR: %s", tmp_dir)
        try:
            os.chdir(tmp_dir)

            cmd_git_clone = ["git", "clone", source_path, module_name]
            subprocess.check_call(cmd_git_clone)

            os.chdir(module_name)

            cmd_git_reset = ["git", "checkout", event["patchSet"]["revision"], "-b", "tmp"]
            subprocess.check_call(cmd_git_reset)

            output_with_patch = run_qdoc(module_name)

            #reseting to parent and cleaning (especially needed for docs removal)
            cmd_git_clean = ["git", "clean", "-fdxq"]
            subprocess.check_call(cmd_git_clean)
            cmd_git_reset = ["git", "reset", "--hard", "HEAD^"]
            subprocess.check_call(cmd_git_reset)

            output_no_patch = run_qdoc(module_name)

            logging.info("DONE RUNNING QDOC")
            return review_output(event, output_no_patch, output_with_patch)

        finally:
            # TODO reuse tmp dir
            logging.info("REMOVING TMP DIR: %s", tmp_dir)
            shutil.rmtree(tmp_dir)
            logging.debug("WORKER EXECUTION TIME: %s", time.time() - start_time)
    except subprocess.CalledProcessError, e:
        logging.error("QDoc sanity failed because of an internal error: %s", e)
        return -1


def watcher():
    while True:
        try:
            ssh = subprocess.Popen(["ssh", config.gerrit_address, "gerrit", "stream-events"], stdout=subprocess.PIPE)
            import multiprocessing
            logging.info("STARTING WATCHER")
            def multiprocess_config_assign(c):
                config = c
            processPool = multiprocessing.Pool(processes=config.workers_count,
                                               initializer=multiprocess_config_assign,
                                               initargs=(config,),
                                               maxtasksperchild=5)
            os.chdir(config.watcher_working_dir)
            event_string = ssh.stdout.readline()
            while len(event_string):
                try:
                    processPool.apply_async(func=process_event, args=(event_string,))
                finally:
                    #clean up working dir is it neccessery?
                    os.chdir(config.watcher_working_dir)
                event_string = ssh.stdout.readline()
            # we can get here if connection was broken somehow for example because of a timeout
            logging.error("WATCHER RESTART because an empty response was received")
            try:
                if ssh.returncode is None:
                    # try to terminate the connection, it is better then wait for gc to do it.
                    logging.warn("WATCHER received empty response but the connection was not closed, about to terminate it before restart")
                    ssh.terminate()
                else:
                    logging.warn("WATCHER was terminated with error code: %s", ssh.returncode)
            except:
                pass
        except:
            # an error occured let's restart in 15 sec
            logging.critical("WATCHER RESTART because of: %s", sys.exc_info())
            import time
            time.sleep(15)


if __name__== "__main__":
    class Config(object): pass
    config = Config()
    import argparse
    parser = argparse.ArgumentParser(prog="QDoc bot",
                   description='It listens to gerrit events and tries to catch all new documentation errors',
                   epilog="QDoc bot takes into consideration different environment variables (like TMP or TEMP). It also may use ccache and icecc if configured correctly")
    parser.add_argument('-j',
                   type=int,
                   dest="workers_count",
                   default=None,
                   help='Workers count, how many parallel builds can be done at the same time. Default is equals to CPU count.')
    parser.add_argument('--addr',
                   type=str,
                   dest="gerrit_address",
                   metavar="gerrit.example.org",
                   default="codereview.qt-project.org",
                   help='Address of the gerrit instance. Default is codereview.qt-project.org')
    parser.add_argument('--dir',
                   type=str,
                   dest="watcher_working_dir",
                   metavar="/home/user/dev/qdoc-watcher",
                   required=True,
                   help='Set working directory which contains all neccessery checkouts')
    parser.add_argument('--log-level',
                   type=str,
                   dest="logging_level",
                   choices=["debug", "info", "warning", "error", "critical"],
                   default="INFO",
                   help='Set verbose level')
    parser.add_argument('--sandbox',
                   dest="sandbox",
                   action="store_true",
                   default=False,
                   help='The option should be used for debugging only. It simulates execution of the bot, post reviews are sent only for 33219 and 33224 changes')

    args = parser.parse_args(namespace=config)
    logging.basicConfig(format='(PID: %(process)d) %(asctime)s %(levelname)s: %(message)s', level=getattr(logging, config.logging_level.upper(), None))
    watcher()
