#!/usr/bin/env python
"""
This script allows the user to submit the calculations contained in the `Flow`.
It provides both a command line interface as well as a graphical interfaced based on wxpython.
"""
from __future__ import print_function, division, unicode_literals

import sys
import os
import argparse
import time

from pprint import pprint
from monty import termcolor
from monty.termcolor import cprint
from pymatgen.io.abinitio.launcher import PyFlowScheduler, PyLauncher
import abipy.abilab as abilab


def straceback():
    """Returns a string with the traceback."""
    import traceback
    return traceback.format_exc()


def as_slice(obj):
    """
    Convert an integer, a string or a slice object into slice.

    >>> assert as_slice(5) == slice(5, 6, 1)
    >>> assert as_slice("[1:4]") == slice(1, 4, 1)
    >>> assert as_slice("1::2") == slice(1, None, 2)
    """
    if isinstance(obj, slice) or obj is None: return obj

    try:
        # integer.
        if int(obj) == float(obj): return slice(int(obj), int(obj)+1, 1)
    except:
        # assume string defining a python slice [start:stop:step]
        if not obj: return None
        if obj.count("[") + obj.count("]") not in (0, 2): 
            raise ValueError("Invalid string %s" % obj)

        obj = obj.replace("[", "").replace("]", "")
        n = obj.count(":") 
        if n == 0:
            obj = int(obj)
            return slice(obj, obj+1)

        tokens = [int(f) if f else None for f in obj.split(":")]
        if len(tokens) == 2: tokens.append(1)
        if tokens[2] is None: tokens[2] = 1

        return slice(*tokens)

    raise ValueError("Cannot convert %s into a slice:\n%s" % (type(obj), obj))


def selected_tasks(flow, options):
    """Return the list of tasks in the flow selected by the user via the command line interface."""
    if options.nids is not None:
        tasks = flow.tasks_from_nids(options.nids)

    elif options.wslice is not None:
        tasks = []
        for work in flow[options.wslice]:
            tasks.extend([t for t in work])
    else:
        # All tasks selected if no option is provided.
        tasks = list(flow.iflat_tasks())

    #print(options, "\nselected_tasks:", tasks)
    return tasks


def selected_nids(flow, options):
    """Return the list of node ids selected by the user via the command line interface."""
    return [task.node_id for task in selected_tasks(flow, options)]


def main():

    def str_examples():
        examples = """\
Usage example:\n
    abirun.py [DIRPATH] single                   => Fetch the first available task and run it.
    abirun.py [DIRPATH] rapid                    => Keep repeating, stop when no task can be executed
                                                    due to inter-dependency.
    abirun.py [DIRPATH] gui                      => Open the GUI 
    nohup abirun.py [DIRPATH] sheduler -s 30 &   => Use a scheduler to schedule task submission

    If DIRPATH is not given, abirun.py automatically selects the database located within 
    the working directory. An Exception is raised if multiple databases are found.

    Options for developers:
        abirun.py prof ABIRUN_OPTIONS      to profile abirun.py
        abirun.py tracemalloc ABIRUN_ARGS  to trace memory blocks allocated by Python
"""
        return examples

    def show_examples_and_exit(err_msg=None, error_code=1):
        """Display the usage of the script."""
        sys.stderr.write(str_examples())
        if err_msg: sys.stderr.write("Fatal Error\n" + err_msg + "\n")
        sys.exit(error_code)

    def parse_nids(s):
        """parse nids argument"""
        if s is None: return s
        try:
            if "," in s:
                return [int(t) for t in s.split(",")]
            else:
                # Convert string to slice and return list.
                s = as_slice(s)
                #print(s)
                if s.stop is None: raise argparse.ArgumentTypeError("stop must be specified")
                return list(range(s.start, s.stop, s.step))
        except:
            raise argparse.ArgumentTypeError("Invalid nids string %s\n Expecting None or int or comma-separated integers or slice sintax" % s)

    def parse_wslice(s):
        s = as_slice(s)
        if s is None: return s
        if s.stop is None: raise argparse.ArgumentTypeError("stop must be specified")
        #return list(range(s.start, s.stop, s.step))
        return s

    # Parent parser for commands that need to know on which subset of tasks/workflows we have to operate.
    # wslide and nids are mutually exclusive.
    flow_selector_parser = argparse.ArgumentParser(add_help=False)
    group = flow_selector_parser.add_mutually_exclusive_group()
    group.add_argument("-n", '--nids', default=None, type=parse_nids, help=(
        "Node identifier(s) used to select the task. Integer or comma-separated list of integers. Use `status` command to get the node ids.\n"
        "Examples: --nids=12 --nids=12,13,16 --nids=10:12 to select 10 and 11, --nids=2:5:2 to select 2,4"  
        ))

    group.add_argument('--wslice', default=None, type=parse_wslice, 
                                      help=("Select the list of works to analyze (python syntax for slices):\n"
                                      "Examples: --wslice=1 to select the second workflow, --wslice=:3 for 0,1,2,"
                                      "--wslice=-1 for the last workflow, --wslice::2 for even indices"))

    #flow_selector_parser.add_argument('--wti', default=None, help="Index of workflow:task")

    # Build the main parser.
    parser = argparse.ArgumentParser(epilog=str_examples(), formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('-v', '--verbose', default=0, action='count', # -vv --> verbose=2
                        help='verbose, can be supplied multiple times to increase verbosity')

    parser.add_argument('--remove-lock', default=False, type=bool, help="Remove the lock file of the pickle file storing the flow.")

    parser.add_argument('--no-colors', default=False, help='Disable ASCII colors')

    parser.add_argument('--loglevel', default="ERROR", type=str,
                        help="set the loglevel. Possible values: CRITICAL, ERROR (default), WARNING, INFO, DEBUG")

    parser.add_argument('path', nargs="?", help=("File or directory containing the ABINIT flow\n" +
                                                 "If not given, the first flow in the current workdir is selected"))

    # Create the parsers for the sub-commands
    subparsers = parser.add_subparsers(dest='command', help='sub-command help', description="Valid subcommands")

    # Subparser for single command.
    p_single = subparsers.add_parser('single', help="Run single task.")

    # Subparser for rapidfire command.
    p_rapid = subparsers.add_parser('rapid', help="Run all tasks in rapidfire mode")

    # Subparser for scheduler command.
    p_scheduler = subparsers.add_parser('scheduler', help="Run all tasks with a Python scheduler.")

    p_scheduler.add_argument('-w', '--weeks', default=0, type=int, help="number of weeks to wait")
    p_scheduler.add_argument('-d', '--days', default=0, type=int, help="number of days to wait")
    p_scheduler.add_argument('-hs', '--hours', default=0, type=int, help="number of hours to wait")
    p_scheduler.add_argument('-m', '--minutes', default=0, type=int, help="number of minutes to wait")
    p_scheduler.add_argument('-s', '--seconds', default=0, type=int, help="number of seconds to wait")

    # Subparser for status command.
    p_status = subparsers.add_parser('status', parents=[flow_selector_parser], help="Show task status.")
    p_status.add_argument('-d', '--delay', default=0, type=int, help=("If 0, exit after the first analysis.\n" + 
                          "If > 0, enter an infinite loop and delay execution for the given number of seconds."))

    # Subparser for cancel command.
    p_cancel = subparsers.add_parser('cancel', parents=[flow_selector_parser], help="Cancel the tasks in the queue.")
    p_cancel.add_argument("-r", "--rmtree", action="store_true", default=False, help="Remove flow directory.")

    # Subparser for restart command.
    p_restart = subparsers.add_parser('restart', help="Restart the tasks of the flow that are not converged.")

    # Subparser for restart command.
    p_reset = subparsers.add_parser('reset', parents=[flow_selector_parser], help="Reset the tasks of the flow with the specified status.")
    p_reset.add_argument('task_status', default="QCritical") 

    # Subparser for unlock command.
    #p_unlock = subparsers.add_parser('unlock', parents=[flow_selector_parser], help="Reset the tasks of the flow with the specified status.")
    #p_reset.add_argument('task_status', default="QCritical") 

    # Subparser for unlock command.
    p_move = subparsers.add_parser('move', help="Move the flow to a new directory and change the absolute paths")
    p_move.add_argument('dest', nargs=1) 

    # Subparser for open command.
    p_open = subparsers.add_parser('open', parents=[flow_selector_parser], help="Open files in $EDITOR, type `abirun.py DIRPATH open --help` for help)")
    p_open.add_argument('what', default="o", 
        help="""\
Specify the files to open. Possible choices:
    i ==> input_file
    o ==> output_file
    f ==> files_file
    j ==> job_file
    l ==> log_file
    e ==> stderr_file
    q ==> qout_file
""")

    p_ncopen = subparsers.add_parser('ncopen', parents=[flow_selector_parser], 
                                      help="Open netcdf files in ipython, type `abirun.py DIRPATH ncopen --help` for help)")
    p_ncopen.add_argument('ncext', nargs="?", default="GSR", help="Select the type of file to open")

    # Subparser for gui command.
    p_gui = subparsers.add_parser('gui', help="Open GUI.")
    p_gui.add_argument("--chroot", default="", type=str, help=("Use chroot as new directory of the flow.\n" +
                       "Mainly used for opening a flow located on a remote filesystem mounted with sshfs.\n" +
                       "In this case chroot is the absolute path to the flow on the **localhost**\n",
                       "Note that it is not possible to change the flow from remote when chroot is used."))

    p_new_manager = subparsers.add_parser('new_manager', parents=[flow_selector_parser], help="Change the TaskManager.")
    p_new_manager.add_argument("manager_file", default="", type=str, help="YAML file with the new manager")

    p_tail = subparsers.add_parser('tail', parents=[flow_selector_parser], help="Use tail to follow the main output file of the flow.")
    p_tail.add_argument('what_tail', nargs="?", type=str, default="o", help="What to follow: o for output (default), l for logfile, e for stderr")

    p_qstat = subparsers.add_parser('qstat', help="Show additional info on the jobs in the queue.")
    #p_qstat.add_argument('what_tail', nargs="?", type=str, default="o", help="What to follow: o for output (default), l for logfile, e for stderr")

    p_deps = subparsers.add_parser('deps', help="Show dependencies.")

    p_robot = subparsers.add_parser('robot', parents=[flow_selector_parser], help="Use a robot to analyze the results of multiple tasks (requires ipython)")
    p_robot.add_argument('robot_ext', nargs="?", type=str, default="GSR", help="The file extension of the netcdf file")

    p_plot = subparsers.add_parser('plot', parents=[flow_selector_parser], help="Plot data")
    p_plot.add_argument("what", nargs="?", type=str, default="ebands", help="Object to plot")

    p_inspect = subparsers.add_parser('inspect', parents=[flow_selector_parser], help="Inspect the tasks")

    p_inputs= subparsers.add_parser('inputs', parents=[flow_selector_parser], help="Show the input files of the tasks")

    p_analyze= subparsers.add_parser('analyze', help="Analyze the results produced by the flow (requires a flow with analyze method)")

    p_docmanager = subparsers.add_parser('docmanager', help="Document the TaskManager options")
    p_docmanager.add_argument("qtype", nargs="?", default=None, help="Document qparams section for the given qtype")

    p_embed = subparsers.add_parser('embed', help=( 
        "Embed IPython. Useful for debugging or for performing advanced operations.\n"
        "THIS OPTION IF FOR EXPERT USERS!"))

    # Parse command line.
    try:
        options = parser.parse_args()
    except Exception as exc: 
        show_examples_and_exit(error_code=1)

    # loglevel is bound to the string value obtained from the command line argument. 
    # Convert to upper case to allow the user to specify --loglevel=DEBUG or --loglevel=debug
    import logging
    numeric_level = getattr(logging, options.loglevel.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError('Invalid log level: %s' % options.loglevel)
    logging.basicConfig(level=numeric_level)

    if options.no_colors:
        # Disable colors
        termcolor.enable(False)

    if options.command == "docmanager":
        print(abilab.TaskManager.autodoc())

        import yaml
        QDICT = yaml.load("""\
priority: 5
queue:
  qtype: slurm
  qname: Oban
  qparams:
      account: user_account
      mail_user: user@mail.com
limits:
  timelimit: 10:00
  min_cores: 3
  max_cores: 16
job:
  mpi_runner: mpirun
  # pre_run is a string in verbatim mode (note |)
  setup:
      - echo ${SLURM_JOB_NODELIST}
      - ulimit -s unlimited
  modules:
      - intel/compilerpro/13.0.1.117
      - fftw3/intel/3.3
  shell_env:
      PATH: /home/user/bin:$PATH
hardware:
   # Mandatory
   num_nodes: 2
   sockets_per_node: 2
   cores_per_socket: 4
   mem_per_node: 8 Gb
""")
        from pymatgen.io.abinitio.qadapters import make_qadapter
        if options.qtype is not None:
            qad = make_qadapter(**QDICT)
            print(qad.QTEMPLATE)
            #print(qad.supported_qparams)

        sys.exit(0)

    # Read the flow from the pickle database.
    if options.path is None:
        # Will try to figure out the location of the Flow.
        options.path = os.getcwd()

    flow = abilab.Flow.pickle_load(options.path, remove_lock=options.remove_lock)
    retcode = 0

    if options.command == "gui":
        if options.chroot:
            # Change the workdir of flow.
            print("Will chroot to %s..." % options.chroot)
            flow.chroot(options.chroot)

        from abipy.gui.flowviewer import wxapp_flow_viewer
        wxapp_flow_viewer(flow).MainLoop()

    elif options.command == "new_manager":
        # Read the new manager from file.
        new_manager = abilab.TaskManager.from_file(options.manager_file)

        # Change the manager of the errored tasks.
        status = "S_QCRITICAL"
        #status = "S_ERROR"
        #print("Resetting tasks with status: %s" % options.task_status)
        for task in flow.iflat_tasks(status=status, nids=selected_nids(flow, options)):
            task.reset()
            task.set_manager(new_manager)
            
        # Update the database.
        return flow.build_and_pickle_dump()

    elif options.command in ("single", "singleshot"):
        nlaunch = PyLauncher(flow).single_shot()
        flow.show_status()
        print("Number of tasks launched: %d" % nlaunch)

    elif options.command in ("rapid", "rapidfire"):
        nlaunch = PyLauncher(flow).rapidfire()
        flow.show_status()
        print("Number of tasks launched: %d" % nlaunch)

    elif options.command == "scheduler":
        sched_options = {oname: getattr(options, oname) for oname in 
            ("weeks", "days", "hours", "minutes", "seconds")}

        if all(v == 0 for v in sched_options.values()):
            sched = PyFlowScheduler.from_user_config()
        else:
            sched = PyFlowScheduler(**sched_options)

        # Check that the env on the local machine is properly setup before starting the scheduler.
        abilab.abicheck()

        sched.add_flow(flow)
        print(sched)
        try:
            sched.start()
        except KeyboardInterrupt:
            # Save the status of the flow before exiting.
            flow.pickle_dump()

    elif options.command == "status":
        if options.delay:
            cprint("Entering infinite loop. Press CTRL+C to exit", color="magenta", end="", flush=True)
            try:
                while True:
                    print(2*"\n" + time.asctime() + "\n")
                    flow.check_status()
                    flow.show_status(verbose=options.verbose, nids=selected_nids(flow, options))
                    if flow.all_ok: break
                    time.sleep(options.delay)
            except KeyboardInterrupt:
                pass
        else:
            flow.show_status(verbose=options.verbose, nids=selected_nids(flow, options))
            if flow.manager.has_queue:
                print("Total number of jobs in queue: %s" % flow.manager.get_njobs_in_queue())

    elif options.command == "open":
        flow.open_files(what=options.what, status=None, op="==", nids=selected_nids(flow, options))

    elif options.command == "ncopen":
        # The name of the method associated to this netcdf file.
        methname = "open_" + options.ncext.lower()
        # List of netcdf file objects.
        ncfiles = [getattr(task, methname)() for task in selected_tasks(flow, options) if hasattr(task, methname)]
        
        if ncfiles:
            # Start ipython shell with namespace 
            import IPython
            if len(ncfiles) == 1:
                IPython.start_ipython(argv=[], user_ns={"ncfile": ncfiles[0]})
            else:
                IPython.start_ipython(argv=[], user_ns={"ncfiles": ncfiles})
        else:
            cprint("Cannot find any netcdf file with extension %s" % options.ncext, color="magenta")

    elif options.command == "cancel":
        print("Number of jobs cancelled %d" % flow.cancel(nids=selected_nids(flow, options)))
        # Remove directory
        if options.rmtree: flow.rmtree()

    elif options.command == "restart":
        nlaunch, excs = 0, []
        for task in flow.unconverged_tasks:
            try:
                fired = task.restart()
                if fired: nlaunch += 1
            except Exception:
                excs.append(straceback())

        cprint("Number of jobs restarted %d" % nlaunch, "blue")
        if nlaunch:
            # update database
            flow.pickle_dump()

        if excs:
            print("Exceptions raised\n")
            pprint(excs)

    elif options.command == "reset":
        print("Will reset tasks with status: %s" % options.task_status)

        count = 0
        for task in flow.iflat_tasks(status=options.task_status, nids=selected_nids(flow, options)):
            print("Resetting task %s" % task)
            task.reset()
            count += 1	

        cprint("%d tasks have been reset" % count, "blue")
        nlaunch = PyLauncher(flow).rapidfire()
        flow.show_status()
        print("Number of tasks launched: %d" % nlaunch)

        if nlaunch == 0:
            deadlocked, runnables, running = flow.deadlocked_runnables_running()
            print("deadlocked:", deadlocked)
            print("runnables:", runnables)
            print("running:", running)
            if deadlocked and not (runnables or running):
                print("*** Flow is deadlocked ***")

        flow.pickle_dump()

    #elif options.command == "unlock":
    #    self.start_lockfile.remove()

    elif options.command == "move":
        print("Will move flow to %s..." % options.dest)
        flow.chroot(options.dest)
        flow.move(options.dest)

    elif options.command == "tail":
        def get_path(task):
            """Helper function used to select the files of a task."""
            choices = {
                "o": task.output_file,
                "l": task.log_file,
                "e": task.stderr_file,
            }
            return getattr(choices[options.what_tail], "path")

        paths = [get_path(task) for task in flow.iflat_tasks(status="Running", nids=selected_nids(flow, options))]

        if not paths:
            cprint("No job is running. Exiting!", "red")
        else:
            cprint("Press CTRL+C to interrupt. Number of output files %d" % len(paths), color="magenta", end="", flush=True)
            try:
                os.system("tail -f %s" % " ".join(paths))
            except KeyboardInterrupt:
                pass

    elif options.command == "qstat":
        for task in selected_tasks(flow, options):
            if not task.qjob: continue
            print("qjob", task.qjob)
            print("info", task.qjob.get_info())
            print("e start-time", task.qjob.estimated_start_time())
            print("qstats", task.qjob.get_stats())

    elif options.command == "deps":
        flow.check_status()
        flow.show_dependencies()

    elif options.command == "robot":
        import IPython
        with abilab.abirobot(flow, options.robot_ext, nids=selected_nids(flow, options)) as robot:
            #IPython.embed(header=str(robot) + "\nType `robot` in the terminal and use <TAB> to list its methods",  robot=robot)
            IPython.start_ipython(argv=[], user_ns={"robot": robot})

    elif options.command == "plot":
        fext = dict(
            ebands="gsr",
        )[options.what]

        open_method = "open_" + fext
        plot_method = "plot_" + options.what

        for task in selected_tasks(flow, options):
            try:
                with getattr(task, open_method)() as ncfile: 
                    print(ncfile)
                    #print(dir(ncfile))
                    getattr(ncfile, plot_method)()
            except:
                pass

    elif options.command == "inspect":
        tasks = selected_tasks(flow, options)

        # Use different thread to inspect the task so that master can catch KeyboardInterrupt and exit.
        # One could use matplotlib non-blocking interface with show(block=False) but this one seems to work well.
        from multiprocessing import Process

        def plot_graphs():
            for task in tasks:
                if hasattr(task, "inspect"):
                    task.inspect()
                else:
                    cprint("Task %s does not provide an inspect method" % task, color="blue")

        p = Process(target=plot_graphs)
        p.start()
        num_tasks = len(tasks)

        if num_tasks == 1:
            p.join()
        else:
            cprint("Will produce %d matplotlib plots. Press CTRL+C to interrupt..." % num_tasks, color="magenta", end="", flush=True)
            try:
                p.join()
            except KeyboardInterrupt:
                print("\nTerminating thread...")
                p.terminate()

    elif options.command == "inputs":
        flow.show_inputs(nids=selected_nids(flow, options))

    elif options.command == "analyze":
        if not hasattr(flow, "analyze"):
            cprint("Flow does not provide the `analyze` method!", "red")
            return 1
            flow.analyze()

    elif options.command == "embed":
        import IPython
        IPython.embed(header="")

    else:
        raise RuntimeError("Don't know what to do with command %s!" % options.command)

    return retcode
    

if __name__ == "__main__":
    # Replace python open to detect open files.
    #from abipy.tools import open_hook
    #open_hook.install()
    retcode = 0
    do_prof, do_tracemalloc = 2* [False]
    try:
        do_prof = sys.argv[1] == "prof"
        do_tracemalloc = sys.argv[1] == "tracemalloc"
        if do_prof or do_tracemalloc: sys.argv.pop(1)
    except: 
        pass

    if do_prof:
        import pstats, cProfile
        cProfile.runctx("main()", globals(), locals(), "Profile.prof")
        s = pstats.Stats("Profile.prof")
        s.strip_dirs().sort_stats("time").print_stats()

    elif do_tracemalloc:
        # Requires py3.4
        import tracemalloc
        tracemalloc.start()

        retcode = main()

        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')

        print("[Top 10]")
        for stat in top_stats[:10]:
            print(stat)
    else:
        sys.exit(main())

    #open_hook.print_open_files()
    sys.exit(retcode)
