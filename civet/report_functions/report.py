import json
import csv
from mako.template import Template
from mako.lookup import TemplateLookup
import datetime as dt
from datetime import date
import collections
from civet import __version__
from civet.report_functions import timeline_functions

from mako.template import Template
from mako.runtime import Context
from mako.exceptions import RichTraceback
from io import StringIO
import os

def make_query_summary_data(metadata, config):
    query_summary_data = []
    with open(metadata, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["query_boolean"] == "True":
                table_row = {}
                for col in config["table_content"]:
                    ## should there be a 'query_boolean' == 'True' statement here?
                    table_row[col] = row[col]
                    
                query_summary_data.append(table_row)
    
    return query_summary_data

def make_fasta_summary_data(metadata,config):

    fasta_summary_pass = []
    fasta_summary_fail = []
    with open(metadata, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["source"] == "input_fasta":
                table_row = {}

                for col in config["fasta_table_content"]:
                    table_row[col] = row[col]
                if row["qc_status"] == "Pass":
                    fasta_summary_pass.append(table_row)
                else:
                    fasta_summary_fail.append(table_row)
    
    return fasta_summary_pass,fasta_summary_fail

def check_earliest_latest_dates(d,catchment_summary_dict,catchment):
    if catchment_summary_dict[catchment]["earliest_date"]:
        if d < catchment_summary_dict[catchment]["earliest_date"]:
            catchment_summary_dict[catchment]["earliest_date"] = d
    else:
        catchment_summary_dict[catchment]["earliest_date"] = d

    if catchment_summary_dict[catchment]["latest_date"]:
        if d > catchment_summary_dict[catchment]["latest_date"]:
            catchment_summary_dict[catchment]["latest_date"] = d
    else:
        catchment_summary_dict[catchment]["latest_date"] = d

def get_top_10_str(total,counter_dict):
    summary = ""
    top = counter_dict.most_common(10)
    remainder_pcent = 100
    for i in top:
        pcent = int(100*(i[1]/total))
        if pcent >= 1:
            remainder_pcent-=pcent
            summary += f"{i[0]} {pcent}% <br>"
    summary += f"Other {remainder_pcent}% <br>"
    return summary

def make_catchment_summary_data(metadata,catchments,config):
    catchment_summary_dict = {}

    for catchment in catchments:
        catchment_summary_dict[catchment] = {
            'total':0
        }

    with open(metadata,"r") as f:
        reader = csv.DictReader(f)

        for row in reader:
            
            if row["query_boolean"] == "False":
                catchment = row["catchment"]

                catchment_summary_dict[catchment]['total'] +=1

                if config["date_column"] in reader.fieldnames:
                    for i in ['earliest_date','latest_date']:
                        if i not in catchment_summary_dict[catchment]:
                            catchment_summary_dict[catchment][i] = ''

                    d = date.fromisoformat(row[config["date_column"]])
                    check_earliest_latest_dates(d,catchment_summary_dict,catchment)

                if config["location_column"] in reader.fieldnames:
                    location_column = config["location_column"]
                    if location_column not in catchment_summary_dict[catchment]:
                        catchment_summary_dict[catchment][location_column] = collections.Counter()
                    if row[location_column] == "":
                        catchment_summary_dict[catchment][location_column]["Unknown"]+=1
                    else:
                        catchment_summary_dict[catchment][location_column][row[location_column]]+=1
                
                if "lineage" in reader.fieldnames:
                    if "lineage" not in catchment_summary_dict[catchment]:
                        catchment_summary_dict[catchment]["lineage"] = collections.Counter()
                    
                    catchment_summary_dict[catchment]["lineage"][row['lineage']]+=1

                if "SNPs" in reader.fieldnames:
                    if "SNPs" not in catchment_summary_dict[catchment]:
                        catchment_summary_dict[catchment]["SNPs"] = collections.defaultdict(list)
                    catchment_summary_dict[catchment]["SNPs"].append(row["SNPs"])

    for catchment in catchment_summary_dict:
        total = catchment_summary_dict[catchment]["total"]
        location_column = config["location_column"]
        if location_column in catchment_summary_dict[catchment]:
            catchment_summary_dict[catchment][location_column] = get_top_10_str(total,catchment_summary_dict[catchment][location_column])
        if "lineage" in catchment_summary_dict[catchment]:
            catchment_summary_dict[catchment]["lineage"] = get_top_10_str(total,catchment_summary_dict[catchment]["lineage"])


    return catchment_summary_dict

def get_timeline(catchment, config):

    timeline_json = timeline_functions.make_timeline_json(catchment, config)

    with open(timeline_json,'r') as f:
        timeline_data = json.load(f)
    
    return timeline_data

def get_snipit(catchments,data_for_report,config):
    for catchment in catchments:
        snipit_svg = ""
        with open(os.path.join(config["data_outdir"],"snipit",f"{catchment}.snipit.svg"),"r") as f:
            for l in f:
                l = l.rstrip("\n")
                snipit_svg+=f"{l}\n"
        data_for_report[catchment]["snipit_svg"] = snipit_svg

def get_newick(catchments,data_for_report,config):
    for catchment in catchments:
        newick = ""
        with open(os.path.join(config["data_outdir"],"catchments",f"{catchment}.tree"),"r") as f:
            for l in f:
                l = l.rstrip("\n")
                newick+=f"{l}\n"
        data_for_report[catchment]["newick"] = newick.rstrip("\n")

def get_background_data(metadata,config):
    background_data = {}

    with open(metadata,"r") as f:
        reader = csv.DictReader(f)
        background_columns = []
        for i in [config["report_column"],"lineage",config["location_column"],config["date_column"]]:
            if i in reader.fieldnames:
                background_columns.append(i)
        for row in reader:
            data = {}
            for i in background_columns:
                data[i] = row[i]
            if row["query_boolean"] == "True":
                data["Query"] = "True"
                background_data[row[config["report_column"]]] = data
            else:
                data["Query"] = "False"
                background_data[row[config["background_column"]]] = data
    data = json.dumps(background_data) 
    return data


def define_report_content(metadata,catchments,config):
    report_content = config["report_content"]
    catchment_id = 0
    data_for_report = {}
    for catchment in catchments:
        data_for_report[catchment] = {}
        catchment_id += 1
        data_for_report[catchment]["catchmentID"]=f"catchment_{catchment_id}"

    if '1' in report_content:
        data_for_report["query_summary_data"] = make_query_summary_data(metadata, config)
        data_for_report["fasta_summary_pass"],data_for_report["fasta_summary_fail"] = make_fasta_summary_data(metadata, config)
    else:
        data_for_report["query_summary_data"] = ""
        data_for_report["fasta_summary_pass"],data_for_report["fasta_summary_fail"] = "",""
    
    if '2' in report_content:
        catchment_summary_data = make_catchment_summary_data(metadata,catchments,config)
        # returns at least a dict with total num in per catchment
        # checks for lineage col, returns lineage counts per catchment
        # checks for location col, returns location counts per catchment
        # checks for date col, finds earliest and latest dates per catchment
        # checks for SNPs col, TO DO: finds 70% consensus of catchment
        
        for catchment in catchments:
            data_for_report[catchment]["catchment_summary_data"] = catchment_summary_data[catchment]
    else:
        for catchment in catchments:
            data_for_report[catchment]["catchment_summary_data"] = ""

    if '3' in report_content:
        get_newick(catchments,data_for_report,config)
    else:
        for catchment in catchments:
            data_for_report[catchment]["newick"] = ""
    
    if '4' in report_content:
        get_snipit(catchments,data_for_report,config)
    else:
        for catchment in catchments:
            data_for_report[catchment]["snipit_svg"] = ""

    if '5' in report_content:
        for catchment in catchments:
            data_for_report[catchment]["timeline_data"] = get_timeline(catchment, config)
    else:
        for catchment in catchments:
            data_for_report[catchment]["timeline_data"] = ""
    
    if '6' in report_content:
        data_for_report[catchment]["map_background"] = ""
    else:
        data_for_report[catchment]["map_background"] = ""
    
    if '7' in report_content:
        data_for_report[catchment]["map_queries"] = ""
    else:
        data_for_report[catchment]["map_queries"] = ""
    
    return data_for_report


def make_report(metadata,report_to_generate,config):
    #need to call this multiple times if there are multiple reports wanted

    catchments = [f"catchment_{i}" for i in range(1,config["catchment_count"]+1)]

    data_for_report = define_report_content(metadata,catchments,config)
    background_data = get_background_data(metadata,config)
    # for i in data_for_report:
    #     print(i, data_for_report[i])
    
    template_dir = os.path.abspath(os.path.dirname(config["report_template"]))
    mylookup = TemplateLookup(directories=[template_dir]) #absolute or relative works

    mytemplate = Template(filename=config["report_template"], lookup=mylookup)
    buf = StringIO()

    ctx = Context(buf, 
                    date = config["date"], 
                    version = __version__, 
                    catchments = catchments, 
                    query_summary_data = data_for_report["query_summary_data"],
                    fasta_summary_pass = data_for_report["fasta_summary_pass"],
                    fasta_summary_fail = data_for_report["fasta_summary_fail"],
                    data_for_report = data_for_report,
                    background_data = background_data,
                    config=config)

    try:
        mytemplate.render_context(ctx)
    except:
        traceback = RichTraceback()
        for (filename, lineno, function, line) in traceback.traceback:
            print("File %s, line %s, in %s" % (filename, lineno, function))
            print(line, "\n")
        print("%s: %s" % (str(traceback.error.__class__.__name__), traceback.error))

    with open(report_to_generate, 'w') as fw:
        fw.write(buf.getvalue())
    
