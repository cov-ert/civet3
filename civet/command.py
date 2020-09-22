#!/usr/bin/env python3
from civet import __version__

import setuptools
import argparse
import os.path
import snakemake
import sys
import tempfile
import csv
import os
import yaml
from datetime import datetime
from Bio import SeqIO
import pkg_resources
from . import _program

from reportfunk.funks import io_functions as qcfunk
from reportfunk.funks import report_functions as rfunk
from reportfunk.funks import custom_logger as custom_logger

thisdir = os.path.abspath(os.path.dirname(__file__))
cwd = os.getcwd()

def main(sysargs = sys.argv[1:]):

    parser = argparse.ArgumentParser(prog = _program, 
    description='civet: Cluster Investivation & Virus Epidemiology Tool', 
    usage='''civet <query> [options]''')

    io_group = parser.add_argument_group('input output options')
    io_group.add_argument('query',help="Input csv file or input config file. CSV minimally has input_column header, Default=`name`. Can include additional fields to be incorporated into the analysis, e.g. `sample_date`")
    io_group.add_argument('-i',"--id-string", action="store_true",help="Indicates the input is a comma-separated id string with one or more query ids. Example: `EDB3588,EDB3589`.", dest="ids")
    io_group.add_argument('-fm','--from-metadata',nargs='*', dest="from_metadata",help="Generate a query from the metadata file supplied. Define a search that will be used to pull out sequences of interest from the large phylogeny. E.g. -fm adm2=Edinburgh sample_date=2020-03-01:2020-04-01")
    io_group.add_argument('-o','--outdir', action="store",help="Output directory. Default: current working directory")
    io_group.add_argument('-f','--fasta', action="store",help="Optional fasta query.", dest="fasta")
    io_group.add_argument('--max-ambig', action="store", default=0.5, type=float,help="Maximum proportion of Ns allowed to attempt analysis. Default: 0.5",dest="maxambig")
    io_group.add_argument('--min-length', action="store", default=10000, type=int,help="Minimum query length allowed to attempt analysis. Default: 10000",dest="minlen")

    data_group = parser.add_argument_group('data source options')
    data_group.add_argument('-d','--datadir', action="store",help="Local directory that contains the data files",default="civet-cat")
    data_group.add_argument('--CLIMB', action="store_true",dest="climb",help="Indicates you're running CIVET from within CLIMB, uses default paths in CLIMB to access data")
    data_group.add_argument("-r",'--remote-sync', action="store_true",dest="remote",help="Remotely access lineage trees from CLIMB")
    data_group.add_argument("-uun","--your-user-name", action="store", help="Your CLIMB COG-UK username. Required if running with --remote-sync flag", dest="uun")
    data_group.add_argument('--input-column', action="store",help="Column in input csv file to match with database. Default: name", dest="input_column",default="name")
    data_group.add_argument('--search-field', action="store",help="Option to search COG database for a different id type. Default: COG-UK ID", dest="data_column",default="central_sample_id")
    data_group.add_argument('-g','--global',action="store_true",dest="search_global",help="Rather than finding closest match in COG database, search globally and find closest match in the entire database.",default=False)

    report_group = parser.add_argument_group('report customisation')
    report_group.add_argument('-sc',"--sequencing-centre", action="store",help="Customise report with logos from sequencing centre.", dest="sequencing_centre")
    report_group.add_argument('--display', action="store", help="Comma separated string of fields to display as coloured dots rather than text in report trees. Optionally add colour scheme eg adm1=viridis", dest="display")
    report_group.add_argument('--fields', action="store",help="Comma separated string of fields to display in the trees in the report. Default: country", dest="tree_fields")
    report_group.add_argument('--label-fields', action="store", help="Comma separated string of fields to add to tree report labels.", dest="label_fields")
    report_group.add_argument("--date-fields", action="store", help="Comma separated string of metadata headers containing date information.", dest="date_fields")
    report_group.add_argument("--node-summary", action="store", help="Column to summarise collapsed nodes by. Default = Global lineage", dest="node_summary")
    report_group.add_argument('--add-bars', action="store_true",help="Render barcharts in the output report", dest="add_bars",default=False)
    report_group.add_argument('--cog-report', action="store_true",help="Run summary cog report. Default: outbreak investigation",dest="cog_report")
    report_group.add_argument('--omit-appendix', action="store_true", help="Omit the appendix section. Default=False", dest="omit_appendix")

    tree_group = parser.add_argument_group('tree context options')
    tree_group.add_argument('--distance', action="store",help="Extraction from large tree radius. Default: 2", dest="distance",type=int,default=2)
    tree_group.add_argument('--up-distance', action="store",help="Upstream distance to extract from large tree. Default: 2", dest="up_distance",type=int,default=2)
    tree_group.add_argument('--down-distance', action="store",help="Downstream distance to extract from large tree. Default: 2", dest="down_distance",type=int,default=2)
    tree_group.add_argument('--collapse-threshold', action='store',type=int,help="Minimum number of nodes to collapse on. Default: 1", dest="threshold", default=1)

    map_group = parser.add_argument_group('map rendering options')
    map_group.add_argument('--local-lineages',action="store_true",dest="local_lineages",help="Contextualise the cluster lineages at local regional scale. Requires at least one adm2 value in query csv.", default=False)
    map_group.add_argument('--date-restriction',action="store_true",dest="date_restriction",help="Chose whether to date-restrict comparative sequences at regional-scale.", default=False)
    map_group.add_argument('--date-range-start',action="store",default="None", type=str, dest="date_range_start", help="Define the start date from which sequences will COG sequences will be used for local context. YYYY-MM-DD format required.")
    map_group.add_argument('--date-range-end', action="store", default="None", type=str, dest="date_range_end", help="Define the end date from which sequences will COG sequences will be used for local context. YYYY-MM-DD format required.")
    map_group.add_argument('--date-window',action="store",default=7, type=int, dest="date_window",help="Define the window +- either side of cluster sample collection date-range. Default is 7 days.")
    map_group.add_argument("--map-sequences", action="store_true", dest="map_sequences", help="Map the coordinate points of sequences, coloured by a trait.")
    map_group.add_argument("--map-cols", required=False, dest="map_cols", help="columns containing EITHER x and y coordinates as a comma separated string OR outer postcodes for mapping sequences")
    map_group.add_argument("--input-crs", required=False, dest="input_crs", help="Coordinate reference system of sequence coordinates")
    map_group.add_argument("--mapping-trait", required=False, dest="mapping_trait", help="Column to colour mapped sequences by")
    
    misc_group = parser.add_argument_group('misc options')
    misc_group.add_argument('-b','--launch-browser', action="store_true",help="Optionally launch md viewer in the browser using grip",dest="launch_browser")
    misc_group.add_argument('--generate-config',dest="generate_config",action="store_true",help="Rather than running a civet report, generate a config file based on the command line arguments provided")
    misc_group.add_argument('-n', '--dry-run', action='store_true',help="Go through the motions but don't actually run")
    misc_group.add_argument('--tempdir',action="store",help="Specify where you want the temp stuff to go. Default: $TMPDIR")
    misc_group.add_argument("--no-temp",action="store_true",help="Output all intermediate files, for dev purposes.")
    misc_group.add_argument('-t', '--threads', action='store',type=int,help="Number of threads",default=1)
    misc_group.add_argument("--verbose",action="store_true",help="Print lots of stuff to screen")
    misc_group.add_argument("-v","--version", action='version', version=f"civet {__version__}")
    
    # Exit with help menu if no args supplied
    if len(sysargs)<1: 
        parser.print_help()
        sys.exit(-1)
    else:
        args = parser.parse_args(sysargs)
    
    
    # create the config dict to pass through to the snakemake file

    config = {
        "trim_start":265,   # where to pad to using datafunk
        "trim_end":29674,   # where to pad after using datafunk
        "up_distance": args.up_distance,
        "down_distance": args.down_distance,
        "distance":args.distance,
        "search_field":args.data_column, 
        "input_column":args.input_column,
        "force":True,
        "date_range_start":args.date_range_start,
        "date_range_end":args.date_range_end,
        "date_window":args.date_window,
        "threshold": args.threshold,
        'date_restriction':args.date_restriction,
        "global_search":args.search_global,
        "delay_collapse": False
        }

    # find the query csv, or string of ids, or config file
    query,configfile = qcfunk.type_input_file(args.query,cwd,config)

    if configfile:
        config = qcfunk.parse_yaml_file(configfile, config)
        
    # find the master Snakefile
    snakefile = qcfunk.get_snakefile(thisdir)
    
    # find the query fasta
    qcfunk.get_query_fasta(args.fasta,cwd, config)

    # default output dir
    qcfunk.get_outdir(args.outdir,cwd,config)

    # specifying temp directory, outdir if no_temp
    tempdir = qcfunk.get_temp_dir(args.tempdir, args.no_temp,cwd,config)

    # check query exists or add ids to temp query file
    qcfunk.check_query_file(query, args.ids,cwd, config)

    # parse the input csv, check col headers and get fields if fields specified
    qcfunk.check_label_and_tree_and_date_fields(args.tree_fields, args.label_fields,args.display, args.date_fields, args.input_column, config)
        
    # map sequences configuration
    qcfunk.map_sequences_config(args.map_sequences,args.mapping_trait,args.map_cols,args.input_crs,config)
    
    # local lineages configuration
    qcfunk.local_lineages_config(args.local_lineages,config)

    # find the data dir
    data_dir = qcfunk.get_datadir(args.climb,args.datadir,args.remote,cwd,config)
    
    # if remote flag, and uun provided, sync data from climb
    qcfunk.get_remote_data(args.remote,args.uun,data_dir,args.datadir,args.climb,config)

    qcfunk.generate_query_from_metadata(args.from_metadata,config)

    # run qc on the input sequence file
    qcfunk.input_file_qc(args.minlen,args.maxambig,config)

    # accessing package data and adding to config dict
    qcfunk.get_package_data(args.cog_report,thisdir,config)

    # get seq centre header file from pkg data
    qcfunk.get_sequencing_centre_header(args.sequencing_centre,config)
    
    # global vs cog db search
    define_seq_db(config)

    # extraction radius configuration
    qcfunk.distance_config(config) #this is now only a print statement because they get added to the config dict up top

    ## report arguments
    # make title
    rfunk.make_title(config)
    # deal with free text
    rfunk.free_text_args(config)
    rfunk.appendix(args.omit_appendix,config)

    #deal with figures
    rfunk.bars(args.add_bars, config)
        
    # summarising collapsed nodes config
    qcfunk.node_summary(args.node_summary,config)
    statsfile = os.path.join(config["outdir"],"stats.json")

 
    if args.launch_browser:
        config["launch_browser"]=True

    # don't run in quiet mode if verbose specified
    if args.verbose:
        quiet_mode = False
        config["quiet_mode"]=False
    else:
        quiet_mode = True
        config["quiet_mode"]=True

    if args.generate_config:
        qcfunk.make_config_file(config)

    

    if args.verbose:
        status = snakemake.snakemake(snakefile, printshellcmds=True,
                                    dryrun=args.dry_run, forceall=True,force_incomplete=True,workdir=tempdir,
                                    config=config, cores=args.threads,lock=False,quiet=False,stats=statsfile
                                    )
    else:
        logger = custom_logger.Logger()
        status = snakemake.snakemake(snakefile, printshellcmds=False,
                                    dryrun=args.dry_run, forceall=True,force_incomplete=True,workdir=tempdir,
                                    config=config, cores=args.threads,lock=False,quiet=True,stats=statsfile,log_handler=logger.log_handler
                                    )

    if status: # translate "success" into shell exit code of 0
       return 0

    return 1

def define_seq_db(config):
    if config["global_search"] == True:
        config["seq_db"] = config["cog_global_seqs"]
    else:
        config["seq_db"] = config["cog_seqs"]


if __name__ == '__main__':
    main()