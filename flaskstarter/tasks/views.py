# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-

from ast import If
from operator import index
from flask import Blueprint, render_template, flash, redirect, url_for, send_file, request, jsonify,session, make_response
import uuid
from flask_login import login_required, current_user
from ..extensions import db, mongo,scfeature
import sys
from flaskstarter.covid2k_meta import covid2k_metaModel
from flaskstarter.tasks.forms import UmapForm
from plotly.subplots import make_subplots
import csv
import gzip
import zipfile
import shutil
import re
import glob
import pandas as pd
import numpy as np
import plotly
import plotly.express as px
import json
from ..utils import TMP_FOLDER
import os
import shortuuid
import subprocess
import pandas as pd
import time
from datetime import datetime
from os.path import exists,basename
import dash_bio
from sklearn import preprocessing
import seaborn as sns
from tqdm import tqdm   
# 0816 Add by junyi
from concurrent.futures import ThreadPoolExecutor
import threading
# 0816 Add by junyi

tasks = Blueprint('tasks', __name__, url_prefix='/tasks')


# set in-memory storage for collection of ids for meta data table display
matrixid = []
collection_searched = []

# sub folders to manage different flask instances: not a good place to put, should be in API endpoint?
user_timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
#user_timestamp = "test"
user_tmp = [TMP_FOLDER + "/" + user_timestamp]
#print(user_tmp)
os.makedirs(user_tmp[-1])


# New view
@tasks.route('/contribute')
def contribute():
    return render_template('tasks/contribute.html')


scClassify_input = []


@tasks.route('/uploader', methods = ['POST'])
def upload_file():
    uploaded_file = request.files['file']
    if uploaded_file.filename != '':
        uploaded_file.save(os.path.join(user_tmp[-1], uploaded_file.filename))
        scClassify_input.extend([uploaded_file.filename])
        flash('scClassify user file uploaded successfully.')

    return redirect(url_for('tasks.contribute'))

# @login_required
@tasks.route('/show_plot', methods=['GET', 'POST'])
def show_plot():     

    # Add initialization of graphJSON incase that return is not refered
    #graphJSON,graphJSON2 = None,None
    cell_color="level2"
    cell_gene=None
    colors=["level2"]
    genes=[]
    import os
    print("Checking worker id")
    print(os.getpid())
    # Get params from html
    cell_color = request.form.get('name_opt_col')
    cell_gene = request.form.get('name_opt_gene')

    try:
        df_genes = pd.read_csv(TMP_FOLDER+"/genes.tsv", sep="\t", header=None)
    except Exception as e:
        print(e)
        print("Error loading genes.tsv" )

    # Create tmpfolder is not exist
    query_timestamp = session.get("sess_timestamp")
    print("Checking user information")
    # user_id = str(current_user.id)
    user_id = session["user_id"]
    print(user_id)
    tmp_folder = os.path.join(user_tmp[-1],user_id,query_timestamp)
    os.makedirs(tmp_folder, exist_ok=True)
    print("Checking collection_searched_query if empty and logged-in user id?")
    print(session["user_id"])
    print(session["query"])
    # Search box is empty
    if(len(session["query"])==0):
        # ID is presented, no meta data:
        if(not (exists(tmp_folder + '/meta.tsv'))):
            meta = mongo.single_cell_meta_country.find({})
            write_file_meta(tmp_folder, meta)
        
        # If ID is presented, no umap:
        elif(not (exists(tmp_folder + '/umap.csv'))):

            pipeline = [
                {"$lookup": { "from": 'umap', "localField": 'id', "foreignField": 'id', "as": 'umap'} }, 
                {"$project": { "umap": 1, "_id": 0 } }, 
                {"$unwind": '$umap' }, 
                {"$replaceRoot": { "newRoot": "$umap" } }
            ]

            umap = mongo.single_cell_meta_country.aggregate(pipeline)

            write_umap(tmp_folder, umap)

    # If search box not empty, write id meta umap
    else:
        print("Search value provided, write id, meta...")
        if isinstance(session["query"], dict):
            print(session["query"])
            meta = mongo.single_cell_meta_country.find(session["query"])
        elif  isinstance(session["query"], list) and len(session["query"]) == 1:
            meta = mongo.single_cell_meta_country.find(session["query"][0])
        else:
            meta = mongo.single_cell_meta_country.find({"$and": session["query"]})    
        #meta = mongo.single_cell_meta_country.find({"$and": session["query"]})
        if isinstance(session["query"], dict):
            print("Getting instance of dict")

            pipeline = [
                    {"$lookup": { "from": 'umap', "localField": 'id', "foreignField": 'id', "as": 'umap'} }, 
                    {"$match": session["query"] }, 
                    {"$project": { "umap": 1, "_id": 0 } }, 
                    {"$unwind": '$umap' }, 
                    {"$replaceRoot": { "newRoot": "$umap" } }
                ]
        elif isinstance(session["query"], list) and len(session["query"]) == 1:
            print("Getting instance of list and getting  first element")
            pipeline = [
                    {"$lookup": { "from": 'umap', "localField": 'id', "foreignField": 'id', "as": 'umap'} }, 
                    {"$match": session["query"][0] }, 
                    {"$project": { "umap": 1, "_id": 0 } }, 
                    {"$unwind": '$umap' }, 
                    {"$replaceRoot": { "newRoot": "$umap" } }
                ]        
        else:
            pipeline = [
                    {"$lookup": { "from": 'umap', "localField": 'id', "foreignField": 'id', "as": 'umap'} }, 
                    {"$match": {"$and": session["query"] }  }, 
                    {"$project": { "umap": 1, "_id": 0 } }, 
                    {"$unwind": '$umap' }, 
                    {"$replaceRoot": { "newRoot": "$umap" } }
            ]
        umap = mongo.single_cell_meta_country.aggregate(pipeline)
        write_file_meta(tmp_folder, meta)
        #umap = mongo.umap.find({'id': {'$in': ids}})
        write_umap(tmp_folder, umap)

        # Assume ids,meta files are provided

        # No cell color is provided
        if(cell_color is None):
            cell_color="level2"
        if(cell_gene is None):
            print("----No gene selected")
        else:
            print("----Gene is selected")

            # The gene name selected is avaliable
            if(cell_gene in df_genes.values):
                # Lookup gene in default dir or user dir based on condition
                flag_same_query =  is_same_query(tmp_folder+"/meta.tsv",collection_searched)
                # Gene table is not cached or the query is differen from the previous
                if((not exists(tmp_folder + '/'+cell_gene+'.tsv')) or 
                (flag_same_query == False)):
                    print("Querying matrix collection...")
                    checkpoint_time = time.time()
                    # use join table - aggregation with matrix table - get gene info
                    if isinstance(session["query"], dict):
                        print("Getting instance of dict")
                        pipeline = [
                                { "$lookup": { "from": 'matrix', "localField": 'id', "foreignField": 'barcode', "as": 'matrix' } }, 
                                { "$match": session["query"]  }, 
                                { "$unwind": "$matrix" }, 
                                { "$match": { "matrix.gene_name": cell_gene }}, 
                                {"$project":  { "matrix": 1, "_id": 0 } }, 
                                { "$replaceRoot": { "newRoot": "$matrix" } } 
                        ]

                    elif isinstance(session["query"], list) and len(session["query"]) == 1:
                        print("Getting instance of list and getting  first element")
                        pipeline = [
                                { "$lookup": { "from": 'matrix', "localField": 'id', "foreignField": 'barcode', "as": 'matrix' } }, 
                                { "$match": session["query"][0]  }, 
                                { "$unwind": "$matrix" }, 
                                { "$match": { "matrix.gene_name": cell_gene }}, 
                                {"$project":  { "matrix": 1, "_id": 0 } }, 
                                { "$replaceRoot": { "newRoot": "$matrix" } } 
                        ]            
                    else:
                         pipeline = [
                                { "$lookup": { "from": 'matrix', "localField": 'id', "foreignField": 'barcode', "as": 'matrix' } }, 
                                { "$match": {"$and": session["query"] }  }, 
                                { "$unwind": "$matrix" }, 
                                { "$match": { "matrix.gene_name": cell_gene }}, 
                                {"$project":  { "matrix": 1, "_id": 0 } }, 
                                { "$replaceRoot": { "newRoot": "$matrix" } } 
                        ]

                    result = mongo.single_cell_meta_country.aggregate(pipeline)
                    #query = mongo.matrix.find({'barcode': {'$in': lookups},'gene_name':cell_gene})
                    print("query finished --- %s seconds ---" % (time.time() - checkpoint_time))

                    ##text=List of strings to be written to file
                    # Force to write to the user folder
                    with open(tmp_folder + '/'+cell_gene+'.tsv', 'w') as file:
                        file.write("\t".join(["_id","gene","barcode",cell_gene]))
                        file.write('\n')
                        for line in result:
                            file.write("\t".join([str(e) for e in line.values()]))
                            file.write('\n')

                    checkpoint_time = time.time()
                    print("write finished --- %s seconds ---" % (time.time() - checkpoint_time))
            else:
                cell_gene = None
                print("Gene not found")
        # Plot umap
        checkpoint_time = time.time()
        graphJSON,graphJSON2,df_plot = plot_umap(cell_color,cell_gene,tmp_folder)
        print("Plot finished --- %s seconds ---" % (time.time() - checkpoint_time))

        # Pass color options to the html
        colors = list(df_plot.columns.values.ravel())
        genes = df_genes.values.ravel()
    return render_template('tasks/show_plot.html', graphJSON=graphJSON,graphJSON2=graphJSON2,colors=colors,genes=genes)

@tasks.route('/show_scfeature', methods=['GET', 'POST'])
def show_scfeature():     

    

    # Get params from html
    #<!-- Change by junyi 2022 0620-->
    #dataset_from_table = request.form.get('name_tbv_dataset')
    celltype_from_table = request.form.get('name_tbv_celltype')


    #print("Receive dataset2 is:",str(dataset_from_table))
    #print("Receive celltype is:",request.form)


    #dataset = request.form.get('name_opt_dataset')
    cell_type = request.form.get('name_opt_celltype')
    feature = request.form.get('name_opt_feature')


    # if(dataset_from_table!=None):

    # if(dataset == None):
    #     dataset = "Arunachalam_2020"

    if(celltype_from_table!=None):
        cell_type = celltype_from_table


    # print("Html params",dataset,cell_type,feature)	
    print("Html params", cell_type, feature)
            
    ### if ... not ... getting metaset
    ### Junyi's code
    # fileds_dataset = mongo.single_cell_meta_country.distinct("meta_dataset")
    # fileds_celltypes = get_field("level2")
    if isinstance(session["query"], dict):
        fileds_celltypes = list(mongo.single_cell_meta_country.find(session["query"], {"meta_sample_id2":1,"_id":0}).distinct("level2"))
    elif isinstance(session["query"], list):
        if len(session["query"]) == 1:
            fileds_celltypes = list(mongo.single_cell_meta_country.find(session["query"][0], {"meta_sample_id2":1,"_id":0}).distinct("level2"))
        else:
            fileds_celltypes = list(mongo.single_cell_meta_country.find({"$and": session["query"]}, {"meta_sample_id2":1,"_id":0}).distinct("level2"))
    # fileds_dataset_2 = mongo.single_cell_meta_country.aggregate(
    #         [
    #             {"$match":{"meta_dataset":dataset}},
    #             {"$group": {"_id": {"meta_dataset": "$meta_dataset", "meta_sample_id2": "$meta_sample_id2"}}}
    #         ]

    # )
    print(fileds_celltypes)
    #mata_sample_id2 = [x["_id"]["meta_sample_id2"] for x in list(fileds_dataset_2)]
    ## Angela's attempt
    print(session["query"])
    if isinstance(session["query"], dict):
        mata_sample_id2 = list(mongo.single_cell_meta_country.find(session["query"], {"meta_sample_id2":1,"_id":0}).distinct("meta_sample_id2"))
    elif isinstance(session["query"], list):
        if len(session["query"]) == 1:
            print("Getting single column filter")
            mata_sample_id2 = list(mongo.single_cell_meta_country.find(session["query"][0], {"meta_sample_id2":1,"_id":0}).distinct("meta_sample_id2"))
        else:
            print("Getting multi-column filter")
            mata_sample_id2 = list(mongo.single_cell_meta_country.find({"$and": session["query"]}, {"meta_sample_id2":1,"_id":0}).distinct("meta_sample_id2"))
    print("Testing Angela's code ...Sample id 2: ",mata_sample_id2)

    # datasets = fileds_dataset
    #dataset =  " ".join(mata_sample_id2)
    dataset= ""
    celltypes = ["All"]
    celltypes=celltypes+fileds_celltypes
    features = []
    
    try:
        # Query propotion
        propotion = scfeature.proportion_raw.find({'meta_dataset': {'$in': mata_sample_id2}})
        df_propotion = pd.DataFrame(list(propotion))
        df_propotion.to_csv(user_tmp[-1]+"/df_proportion_raw_"+dataset+".csv")
        df_d = df_propotion.drop(columns=["_id","meta_scfeature_id"])
        df_melt=df_d.melt(id_vars=['meta_dataset','meta_severity'],value_name="propotion",var_name="cell_type")
        fig = px.bar(df_melt, x="meta_dataset", y="propotion", color="cell_type",facet_col = "meta_severity",template="plotly_white",
        color_discrete_sequence=sns.color_palette("tab20").as_hex())
        fig.update_xaxes(matches=None)
        fig.update_layout(
             title={
                'text': "Overview: cell type proportion in " + dataset,
                'x':0.5,
                'xanchor': 'center'},
            autosize=True, width=1200, height=600
        )
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    except Exception as e:
        graphJSON = None
        print("Error generating figure propotion",e)
    
    if(cell_type == "All"):	
        graphJSON2 = None
    else:
        try:
            # Query dendrogram for each gene
            print("Getting dendrogram information from db")
            gene_prop_celltype = scfeature.gene_prop_celltype.find({'meta_dataset': {'$in': mata_sample_id2}})
            df_gene_prop_celltype = pd.DataFrame(list(gene_prop_celltype))
            df_gene_prop_celltype.to_csv(user_tmp[-1]+"/df_gene_prop_celltype_"+dataset+".csv")
            df_gene_prop_celltype = df_gene_prop_celltype.drop(columns=["_id"])
            if(not(cell_type in celltypes)):
                graphJSON2 = None
            else:
                select_type = cell_type
                fig2 = process_dendrogram(df_gene_prop_celltype,select_type,title="Marker gene proportions of cell types in " + dataset)
                graphJSON2 = json.dumps(fig2, cls=plotly.utils.PlotlyJSONEncoder)
        except Exception as e:
            graphJSON2 = None
            print("Error generating figure dendrogram",e)

    try:
        # Query boxplot
        print("Getting dendrogram information from db")
        pathway_mean = scfeature.pathway_mean.find({'meta_dataset': {'$in': mata_sample_id2}})
        print("Getting pathway mean information into dataframe")
        df_pathway_mean = pd.DataFrame(list(pathway_mean))
        df_pathway_mean.to_csv(user_tmp[-1]+"/df_pathway_mean_"+dataset+".csv")
        df_pathway_mean = df_pathway_mean.drop(columns=["_id"])
        print("Getting boxplot")
        print(cell_type)
        print(dataset)
        print(feature)
        fig3,features = process_boxplot(df_pathway_mean,cell_type,plot_type="pathway",feature=feature,title="Pathway mean scores of: "+ cell_type + " cell types in dataset "+ dataset)

        if(feature is None):
            graphJSON3 = None
        elif(not(feature in features)):
            graphJSON3 = None
        else:
            graphJSON3 = json.dumps(fig3, cls=plotly.utils.PlotlyJSONEncoder)
    
        if(cell_type == "All"):	
            graphJSON4 = None
        elif(not(cell_type in celltypes)):
            graphJSON4 = None
        else:
            select_type = cell_type
            fig4 = process_dendrogram(df_pathway_mean,select_type,plot_type="pathway",title="Pathway mean scores in dataset" + dataset)
            graphJSON4 = json.dumps(fig4, cls=plotly.utils.PlotlyJSONEncoder)

    except Exception as e:
        graphJSON3 = None
        graphJSON4 = None
        print("Error generating figure boxplot",e)


    #return render_template('tasks/show_scfeature.html', graphJSON=graphJSON,graphJSON2=graphJSON2,graphJSON3=graphJSON3,graphJSON4=graphJSON4,datasets=datasets,celltypes=celltypes,features=features)
    return render_template('tasks/show_scfeature.html', graphJSON=graphJSON,graphJSON2=graphJSON2,graphJSON3=graphJSON3,graphJSON4=graphJSON4,celltypes=celltypes,features=features)

## Add by junyi
def process_dendrogram(data,cell_type,plot_type="gene",title="Title"):
    data= data.set_index("meta_dataset")

    if(plot_type=="gene"):
        celltype = data.columns.values
        celltype = np.array([x.split('--')[0] for x in celltype] )
    else:
        data = data.drop(columns=["meta_scfeature_id"])
        celltype = data.columns[2:].values
        celltype = np.array([x.split('--')[1] for x in celltype] )

    data_patient = data.index.values 
    condition = data.meta_severity.values 

    if(cell_type in celltype):

        if(plot_type=="gene"):
            data = data.iloc[:, np.where(celltype == cell_type)[0]] 
        else:
            colNames = data.columns[data.columns.str.contains(pat = "--"+cell_type)] 
            data = data.loc[:,colNames]
    else:
        return None

    condition_colour =['#f00314', '#ff8019',   
                                '#3bb5ff', '#0500c7' , '#5c03fa', '#de00ed' , '#fae603']
    remove =  np.where( np.array( data.sum(axis=0)  ) == 0)[0]
    if remove.size > 0:
        data.drop(data.columns[remove],axis=1,inplace=True) 
    data_np = np.array( data )
    top_feature = np.var(data_np, axis = 0) 
    top_feature = np.argsort(top_feature)
    top_feature = top_feature[::-1][0:50]

    data = data.iloc[:,top_feature ]

    data["condition"] = condition
    my_palette = dict(zip( set(condition ) , condition_colour[0:len(set(condition))]))
    col_colors = data.condition.map(my_palette)

    data = data.drop('condition', 1)
    data = data.transpose()

    x = data.transpose().values 
    min_max_scaler = preprocessing.MinMaxScaler()
    x_scaled = min_max_scaler.fit_transform(x)
    df = pd.DataFrame(x_scaled)
    df = df.transpose()
    df.columns = data.columns
    df.index = data.index

    if(plot_type!="gene"):
        df = df.transpose()


    fig2 = dash_bio.Clustergram(
        data=df,
        column_labels=list(df.columns.values),
        row_labels=list(df.index),
        #column_colors= list(col_colors),
        #row_colors_label= "Condition",
        color_map= [
        [0.0, '#000080'],
        [0.5, '#ffffff'],
        [1.0, '#ff0000']
        ],
        height=1000,
        width=1200
    )
    fig2.update_layout(
        title={
        'text': title,
        'y':0.95,
        'x':0.5,
        'xanchor': 'center',
        'yanchor': 'top'}
    )   

    #fig2.update_layout(title_text='Pie',layout_showlegend=False)    
    return fig2

def process_boxplot(input_data,cell_type,plot_type="gene",feature=None,title="Title"):


    data = input_data.set_index("meta_scfeature_id")
    data = data.drop(columns=['meta_dataset','meta_severity'])

    columns = data.columns.values
    
    if(plot_type=="gene"):
        celltypes = np.array([x.split('--')[0] for x in columns] )
        # if(feature is None):
        #     feature = "KLF6"
        features = list(set(np.array([x.split('--')[1] for x in columns] )))
    else:
        celltypes = np.array([x.split('--')[1] for x in columns] )
        # if(feature is None):
        #     feature = "HALLMARK-ADIPOGENESIS"            
        features = list(set(np.array([x.split('--')[0] for x in columns] )))
    if(not(feature in features)):
        feature = features[0]           
    features.sort()
    if(not(cell_type is None)):
        if(not(cell_type == "All")):
            data = data.iloc[:, np.where(celltypes == cell_type)[0]] 

    data_patient = data.index.values 
    data["patient"] = [x.split('_cond_')[0] for x in data_patient] 
    data["condition"] = [x.split('_cond_')[1] for x in data_patient] 
  
    data=data.melt(id_vars=['patient','condition'])
    data = data[data["variable"].str.contains(feature) ]

    fig = px.box(data,  x="variable", y="value",color="condition",color_discrete_sequence=
            ['#3D9970','#FF851B','#FF4136'],template="plotly_white",
            category_orders={'condition': ['Healthy','Mild/Moderate','Severe/Critical']},
            )
    fig.update_layout(
            title={
                'text': title,
                'x':0.5,
                'xanchor': 'center'},

            autosize=False, width=1200, height=800,
            #legend_traceorder="reversed",
            # legend=dict(
            #         title=None, orientation="h", y=0, yanchor="top", x=0.5, xanchor="center"
            #     )
            )

    return fig, features

def plot_tse():
    df = pd.read_csv(user_tmp[-1] + '/umap.csv', index_col=0)

    l = []
    for i in df.index:
        # print(df.loc[i].values)
        l.append(df.loc[i].values)
    sln = np.stack(l)
    projections = sln
    fig = px.scatter(
        projections,template="plotly_white", x=0, y=1)
    fig.update_layout(
        autosize=False, width=900, height=600
    )
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graphJSON

def plot_stack_bar(df):
    l = []
    fig = px.histogram(df, x="sex", y="total_bill",
                color='smoker', barmode='group',template="plotly_white",
                height=400)
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graphJSON

## Create by junyi
def plot_umap(cell_color='scClassify_prediction',gene_color=None,tmp_folder="."):
    df = pd.read_csv(tmp_folder + '/umap.csv', index_col=0)
    df.columns = ["umap_0","umap_1"]
    df_meta = pd.read_csv(tmp_folder + '/meta.tsv', index_col=1,sep="\t")
    df_plot = df.merge(df_meta, left_index=True, right_index=True)



    if(not(gene_color is None)):
        df_gene = pd.read_csv(tmp_folder + '/'+gene_color+'.tsv',sep="\t", index_col=2)
        df_plot = df_plot.merge(df_gene, left_index=True, right_index=True,how="left")
        print(df_plot.shape)
        df_plot[gene_color] = df_plot[gene_color].fillna(value=0)
        #df_plot[gene_color] = df_plot[gene_color].fillna(value=0)
        #fig2 = px.violin(df_plot, y=gene_color, x=cell_color, box=False, points=False)
        #df_plot[gene_color] = np.clip(df_plot[gene_color],np.percentile(df_plot[gene_color], 5),np.percentile(df_plot[gene_color], 95))
        fig2 = px.box(df_plot, y=gene_color, x=cell_color,color=cell_color,template="plotly_white",color_discrete_sequence=
            ["#F8A19F","#8E321C","#F6222E","#F1CE63","#B6992D","#59A14F","#499894","#4E79A7",
            "#A6AAFE","#5930FB","#500EE2","#7427B9","#931ADD","#A04DB9","#C585AF","#B8418A","#AD0267","#7A325C","#cccccc","#b2b2b2"])

        fig2.update_layout(
        autosize=False, width=900, height=600)
        graphJSON2 = json.dumps(fig2, cls=plotly.utils.PlotlyJSONEncoder)
        fig = px.scatter(
            df_plot, x="umap_0", y="umap_1",template="plotly_white",color=gene_color,color_continuous_scale="Viridis")
        fig.update_layout(
                autosize=False, width=900, height=600)
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


    else:
        fig = px.scatter(
            df_plot, x="umap_0", y="umap_1",template="plotly_white",color=cell_color,color_discrete_sequence=
            ["#F8A19F","#8E321C","#F6222E","#F1CE63","#B6992D","#59A14F","#499894","#4E79A7",
            "#A6AAFE","#5930FB","#500EE2","#7427B9","#931ADD","#A04DB9","#C585AF","#B8418A","#AD0267","#7A325C","#cccccc","#b2b2b2"]
            ,color_continuous_scale="Viridis")
        fig.update_layout(
                autosize=False, width=900, height=600)
        graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        fig2 = None
        graphJSON2 = None

    return graphJSON,graphJSON2,df_plot


@tasks.route('/run_scclassify', methods=['GET', 'POST'])
def run_scClassify():
    print("running scClassify...")
    scClassify_folder = TMP_FOLDER + "/scClassify"
    scClassify_code_path = scClassify_folder + "/scClassify_example_codes.r"
    scClassify_model_path = scClassify_folder + "/scClassify_trainObj_trainWillks_20201018.rds"
    scClassify_input_path = user_tmp[-1] + "/" + scClassify_input[-1]
    scClassify_output_path = user_tmp[-1] + "/scClassify_predicted_results.csv"
    ret = subprocess.call("Rscript %s %s %s %s" % (scClassify_code_path, scClassify_input_path, scClassify_model_path, scClassify_output_path), shell=True)
    if ret != 0:
        if ret < 0:
            print("Killed by signal")
        else:
            print("Command failed with return code %s" % ret)
    else:
        print("SUCCESS!!")
        flash("SUCCESS!!")
        return redirect(url_for('tasks.contribute'))


@tasks.route('/download_scClassify',methods=['POST'])
def download_scClassify():
    return send_file(user_tmp[-1] + "/scClassify_predicted_results.csv", as_attachment=True)

# here
@tasks.route('/table_view', methods=['POST', 'GET'])
# @login_required
def table_view():
    fsampleid = get_field("meta_sample_id2")
    fage = get_field("meta_age_category")
    print(fage)
    fdonor = get_field("meta_patient_id")
    fprediction = get_field("level2")
    fstatus = get_field("meta_severity")
    fdataset = get_field("meta_dataset")
    fcountry = get_field("pbmc.Country")
    if "main" in request.args:
        l = request.args["main"]
        if l == "":
            return render_template('tasks/table_view.html',
                                   fdonor=fdonor,
                                   fage=fage,
                                   fsampleid=fsampleid,
                                   fprediction=fprediction,
                                   fstatus=fstatus,
                                   fdataset=fdataset,
                                   fcountry=fcountry,
                                   link=l)
    else:
        l = None
    return render_template('tasks/table_view.html',
                           fdonor=fdonor,
                           fage=fage,
                           fsampleid=fsampleid,
                           fprediction=fprediction,
                           fstatus=fstatus,
                           fdataset=fdataset,
                           fcountry=fcountry,
                           link=l)


#ids = [x["_id"] for x in list(db.single_cell_meta_country.find({}, {"_id": 1}))]

data = []


# Write big file
def write_file_byid(path, towrite):
    fn = os.path.join(path,'ids.csv')
    print('writing ids to' + fn)
    file = open(fn, 'w+', newline='\n')
    #print(towrite[0])
    data = [[r['id']] for r in towrite]
    #print(data)
    with file:
        write = csv.writer(file)
        write.writerows(data)

# Write id meta file
def write_id_meta(path, towrite):
    fid = os.path.join(path,'ids.csv')
    fmeta = os.path.join(path,'meta.tsv')

    print('writing ids and meta')
    ids = []
    with open(fid, 'w') as file_id,open(fmeta, 'w') as file_meta:
        file_meta.write("\t".join([str(e) for e in towrite[0].keys()]))
        file_meta.write('\n')

        for r in towrite:
            # Writ id
            row = str(r['id'])
            file_id.write(row)
            file_id.write('\n')
            ids.append(row)
            # Writ meta
            file_meta.write("\t".join([str(e) for e in r.values()]))
            file_meta.write('\n')
    return ids

# Write file
def write_file_meta(path, towrite):
    fn = os.path.join(path,'meta.tsv')
    print('writing meta to' + fn)

    fields = [
    '_id','id','barcode','meta_dataset','meta_tissue','meta_sample_type',\
    'meta_protocol','meta_technology','meta_sample_id','meta_patient_id',\
    'meta_sample_time','meta_disease','meta_severity','meta_WHO_scores',\
    'meta_outcome','meta_days_from_onset_of_symptoms','meta_ethinicity',\
    'meta_gender','meta_age','meta_BMI','meta_PreExistingHypertension',\
    'meta_PreExistingHeartDisease','barcodes','level1','level2','level3',\
    'meta_sample_id2','meta_age_category', 'country']
    ##text=List of strings to be written to file
    #print(towrite[0])
    with open(fn, 'w') as file:
        file.write("\t".join(fields))
        file.write('\n')

        # for line in towrite:
        #     file.write("\t".join([str(e) for e in line.values()]))
        #     file.write('\n')
        for num, doc in enumerate(towrite):
            # convert ObjectId() to str
            file.write("\t".join([str(e) for e in doc.values()]))
            file.write('\n')


    # docs = pd.DataFrame(columns=fields)

    # for num, doc in enumerate(towrite):
    #     # convert ObjectId() to str
    #     doc["_id"] = str(doc["_id"])
    #     # get document _id from dict
    #     doc_id = doc["_id"]
    #     # create a Series obj from the MongoDB dict
    #     series_obj = pd.Series(doc, name=doc_id)
    #     # append the MongoDB Series obj to the DataFrame obj
    #     docs = pd.concat( [docs,series_obj] )

    # # export MongoDB documents to CSV
    # #csv_export = docs.to_csv(sep="\t") # CSV delimited by commas
    # #print ("\nCSV data:", csv_export)
    # # export MongoDB documents to a CSV file
    # docs.to_csv(fn,sep="\t", index=False)


def write_umap(path, towrite):
    fn = path + '/umap.csv'
    print('writing umap to' + fn)
    with open(fn, 'w') as file:
        for r in towrite:
            file.write(",".join([str(r['id']), str(r['UMAP1']), str(r['UMAP2'])]))
            file.write('\n')
    return fn

# 0816 deprecated by junyi
def write_10x_mtx_old(path,gene_dict, barcode_dict, doc_count, towrite):
    fn = path + '/matrix.mtx'
    print('writing matrix.mtx to' + fn)
    ##text=List of strings to be written to file
    with open(fn, 'w') as file:
        file.write("%%MatrixMarket matrix coordinate real general")
        file.write('\n')
        # gene_dict length
        file.write(" ".join([str(len(gene_dict)), str(len(barcode_dict)), str(doc_count)]))
        file.write('\n')
        for line in tqdm(towrite, total=doc_count):
        #for line in towrite:
            # gene = mongo.genes.find_one({"gene_name":line["gene_name"]},{"gene_id":1, "_id":0})
            file.write(" ".join([             
                str(gene_dict[line['gene_name']]),
                str(barcode_dict[line['barcode']]),
                str(line['expression']),
            ]))
            file.write('\n')  
# 0816 deprecated by junyi

# 0816 added by junyi
def write_10x_mtx(path,gene_dict, barcode_dict, doc_count, towrite):
    fn = path + '/matrix.mtx'
    print('writing matrix.mtx to' + fn)
    ##text=List of strings to be written to file

    def write_file_line(path, data,gene_dict,barcode_dict):
        try:
            file = open(path, "a")
            while True:
                line = next(data,None)
                file.write(" ".join([             
                    str(gene_dict[line['gene_name']]),
                    str(barcode_dict[line['barcode']]),
                    str(line['expression']),"\n",
                ]))
        except StopIteration:
            print("Finish writing file")
            file.close()
        except Exception as e:
            file.write(str(e))
            file.write(str(len(gene_dict)))
            file.write(str(len(barcode_dict)))
            file.close()
        finally:
            file.close()


    with open(fn, 'w') as file:
        file.write("%%MatrixMarket matrix coordinate real general")
        file.write('\n')
        # gene_dict length
        file.write(" ".join([str(len(gene_dict)), str(len(barcode_dict)), str(doc_count)]))
        file.write('\n')
    
    try:
        data_buff = []
        file = open(fn, "a")
        while True:
            line = next(towrite,None)
            data_buff.append(" ".join([             
                    str(line['gene_name']),
                    str(line['barcode']),
                    str(line['expression']),
                ]))
            data_buff.append("\n")
            # file.write(" ".join([             
            #     str(line['gene_name']),
            #     str(line['barcode']),
            #     str(line['expression']),
            # ]))
            # file.write('\n') 
            if len(data_buff) >= 10000:
                file.writelines(data_buff)
                data_buff = []

    except StopIteration:
        print("Finish writing file")
        file.writelines(data_buff)
        data_buff = []

        file.close()
    except Exception as e:
        file.write(str(e))
        data_buff = []

        print("Error writing file")
        file.close()
    finally:
        data_buff = []
        file.close()

    # Nthreads = 8
    # for t in range(Nthreads):
    # thread1 = threading.Thread(target=write_file_line, args=[fn+str(1), towrite,gene_dict,barcode_dict])
    # thread2 = threading.Thread(target=write_file_line, args=[fn+str(2), towrite,gene_dict,barcode_dict])
    # thread1.start()
    # thread2.start()
    # thread1.join()
    # thread2.join()
# 0816 added by junyi

def is_same_query(meta_path,collection_searched):
    try:
        df_meta = pd.read_csv(meta_path, index_col=1,sep="\t")
        _ids = list(df_meta._id.values)
        _ids.sort()
        oid = [str(_id) for _id in collection_searched]
        oid.sort()
    except:
        print("Error when comparing query, return false")
        return False    

    return _ids == oid

def remove_files(path):
    for f in [
        path + '/ids.csv',
        path + '/matrix.zip',
        path + '/matrix.mtx.gz',
        path + '/genes.tsv.gz',
        path + '/barcodes.tsv.gz',
        path + '/meta.tsv']:
        if((exists(f))):
            shutil.os.remove(f)

def store_queryinfo(session,force=True):
    session.permanent = False
    sess_timestamp = session.get("sess_timestamp")
    if(force==True):
        print("Pop old session timestamp")
        new_timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
        session["sess_timestamp"] = new_timestamp
    else:
        if((sess_timestamp==None)):
            new_timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            session["sess_timestamp"] = new_timestamp
        
    return session


# Download big file
# @login_required
@tasks.route('/download_meta',methods=['POST'])
def download_meta():
    user_timestamp = session.get("sess_timestamp")
    user_id = session["user_id"]
    # user_id = str(current_user.id)
    tmp_folder = os.path.join(user_tmp[-1],user_id,user_timestamp)
    session["tmp_folder"] = tmp_folder
    os.makedirs(tmp_folder, exist_ok=True)
    if isinstance(session["query"], dict):
        meta = mongo.single_cell_meta_country.find(session["query"]) 
    elif isinstance(session["query"], list) and len(session["query"]) == 1:
        print(session["query"])
        meta = mongo.single_cell_meta_country.find(session["query"][0])
    else:
        meta = mongo.single_cell_meta_country.find({"$and": session["query"]})


    print('writing ids to csv file only once, firstly load the data')
    #write_file_byid(tmp_folder, meta) # ids.csv is used in download_matrix barcode_dict
    write_file_meta(tmp_folder, meta)
    return send_file(os.path.join(tmp_folder,'meta.tsv'), as_attachment=True)

# Download big file
@tasks.route('/download_scfeature',methods=['POST'])
def download_scfeature():
    list_files = glob.glob( user_tmp[-1]+"/*_gene_prop_celltype*.csv")+\
    glob.glob( user_tmp[-1]+"/*_pathway_mean*.csv")+\
    glob.glob( user_tmp[-1]+"/*_proportion_raw*.csv")

    if(not (exists(user_tmp[-1] + '/scfeature.zip'))):
        with zipfile.ZipFile(user_tmp[-1] + '/scfeature.zip', 'w') as zipMe:        
            for file in list_files:
                if(exists(file)):
                    zipMe.write(file,arcname=basename(file), compress_type=zipfile.ZIP_DEFLATED)

    return send_file(user_tmp[-1] + '/scfeature.zip', as_attachment=True)


# @login_required
@tasks.route('/download_matrix',methods=['POST'])
def download_matrix():

    user_timestamp = session.get("sess_timestamp")
    user_id = session["user_id"]
    # user_id = str(current_user.id)
    tmp_folder = os.path.join(user_tmp[-1],user_id,user_timestamp)
    session["tmp_folder"] = tmp_folder
    os.makedirs(tmp_folder, exist_ok=True)

    # No query is search, then we use default use case:
    if(len(session["query"])==0):
        return send_file(TMP_FOLDER+'/default/matrix.zip', as_attachment=True)
    else:
        # If query is presented, remove the result old queries regardlessly for secure download
        remove_files(tmp_folder)
        if isinstance(session["query"], dict):
            meta = mongo.single_cell_meta_country.find(session["query"]) 
        elif isinstance(session["query"], list):
            if len(session["query"]) == 1:
                print(session["query"])
                meta = mongo.single_cell_meta_country.find(session["query"][0])
            else:
                meta = mongo.single_cell_meta_country.find({"$and": session["query"]})
        write_id_meta(tmp_folder, meta)
    # Down load 10x matrix if not exist
    if(not (exists(tmp_folder + '/matrix.mtx.gz'))):
        start_time2 = time.time()
        if isinstance(session["query"], dict):
            print("Getting instance of dict")
            pipeline = [
                {"$lookup": { "from": 'matrix', "localField": 'id', "foreignField": 'barcode', "as": 'matrix'} }, 
                {"$match": session["query"] }, 
                {"$project": { "matrix": 1, "_id": 0 } }, 
                {"$unwind": '$matrix' }, 
                {"$replaceRoot": { "newRoot": "$matrix" } }
            ]
        elif isinstance(session["query"], list) and len(session["query"]) == 1:
            print("Getting instance of list and getting  first element")
            pipeline = [
                {"$lookup": { "from": 'matrix', "localField": 'id', "foreignField": 'barcode', "as": 'matrix'} }, 
                {"$match": session["query"][0] }, 
                {"$project": { "matrix": 1, "_id": 0 } }, 
                {"$unwind": '$matrix' }, 
                {"$replaceRoot": { "newRoot": "$matrix" } }
            ]        
        else:
            pipeline = [
                {"$lookup": { "from": 'matrix', "localField": 'id', "foreignField": 'barcode', "as": 'matrix'} }, 
                {"$match": {"$and": session["query"] }  }, 
                {"$project": { "matrix": 1, "_id": 0 } }, 
                {"$unwind": '$matrix' }, 
                {"$replaceRoot": { "newRoot": "$matrix" } }
            ]

        mtx = mongo.single_cell_meta_country.aggregate(pipeline, allowDiskUse=False)

        with open(tmp_folder + '/query.txt', 'a') as file:
            file.write(str(session["query"]))
            file.write('\n')
    


        print("query finished --- %s seconds ---" % (time.time() - start_time2))

        start_time2 = time.time()
        # temporary check of length of matrix returned
        #doc_count = 1
        #{$setWindowFields: {output: {totalCount: {$count: {}}}}}
        #mtx = mongo.single_cell_meta_country.aggregate(pipeline + [{"$setWindowFields": {"output": {"totalCount": {"$count": {}}}}}],allowDiskUse=True)
        #doc_count = next(x["totalCount"] for x in mtx if x)
        #print(doc_count)
        #explain = mongo.command('aggregate', "matrix", pipeline=pipeline, explain=True)
        #print(explain)
        doc_count = 1
        print("list finished --- %s seconds ---" % (time.time() - start_time2))

        ## Parse the barcode and gene based on name 
        def get_dict(path, sep="\t", header=None, save_path=None):
            # Transfrom the gene/barcode name to the corresponding number
            df_read = pd.read_csv(path, sep=sep, header=header)
            row_num = [i for i in range(1, len(df_read)+1)]
            #print(row_num)
            row_name = list(df_read.iloc[:, 0].values)
            #print(row_name)
            result_dict = dict(zip(row_name, row_num))
            #print(result_dict)
            if(not(save_path is None)):
                df_read.to_csv(save_path, sep="\t", header=False, index=False, compression='gzip')
            return result_dict

        # Save gene name
        if(not (exists(tmp_folder + '/genes.tsv.gz'))):
            dict_gene = get_dict(TMP_FOLDER + "/genes.tsv", save_path=tmp_folder + "/genes.tsv.gz")
        # Save barcodes
        if(not (exists(tmp_folder + '/barcodes.tsv.gz'))):
            #write_file_byid(tmp_folder, meta)
            # todo: this line will error if try download_mtx in show_plot page after gene is selected. as barcodes are not generated
            dict_barcode = get_dict(tmp_folder + "/ids.csv", sep=",", save_path=tmp_folder + "/barcodes.tsv.gz")
        
        # Print start time for writing matrix
        start_time_wrtie = time.time()
        write_10x_mtx(tmp_folder, dict_gene, dict_barcode, doc_count, mtx)
        print("Write 10x mtx finished --- %s seconds ---" % (time.time() - start_time_wrtie))

    if(not (exists(tmp_folder + '/matrix.zip'))):
        list_files = [
            tmp_folder + '/matrix.mtx',
            tmp_folder + '/genes.tsv.gz',
            tmp_folder + '/barcodes.tsv.gz',
            tmp_folder + '/meta.tsv'
        ]
        checkpoint_time = time.time()
        with zipfile.ZipFile(tmp_folder + '/matrix.zip', 'w') as zipMe:        
            for file in list_files:
                if(exists(file)):
                    zipMe.write(file,arcname=basename(file), compress_type=zipfile.ZIP_DEFLATED)
        print("zipping finished --- %s seconds ---" % (time.time() - checkpoint_time))

    response = make_response(send_file(tmp_folder + '/matrix.zip', as_attachment=True))
    print("setting cookies")
    response.set_cookie(key='downloadID', value=user_id,max_age=1)
    return response

# Constructor for column-filter after multi-select
def query_builder(map):
    construct = []
    re_match = re.compile(r'^\d{1,10}\.?\d{0,10}$')
    for k in map:
        if (k in ["meta_age_category", "meta_sample_id2", "meta_dataset", "level2", "meta_severity", "meta_patient_id", "pbmc.Country"]):
            l = []
            for ki in map[k]:
                if re_match.findall(ki):
                    # if string only contains numbers, we need to convert it to integer to search
                    # age contains strings and integers, but the front-end will always process them to strings
                    if ki.isdigit():
                        l.append(int(ki))
                    else:
                        l.append(int(float(ki)))
                else:
                    l.append(ki)
            q = {k: {"$in": l}}
            print(q)
            construct.append(q)
        else:
            print(map[k])

    print(construct)
    return construct

# Pagination algorithm by skiplimit return ajax data source and total records for datatable data pagination
def paginate_skiplimit(page_size, page_no, search_type, search_params):
    # Calculate number of documents to skip
    print("Using Pagination by mongodb skip-limit")
    skips = page_size * (page_no - 1)
  
    # search type 1 - no search: by default search value is empty ''
    if search_type == "default":
        tmp = mongo.single_cell_meta_country.find().skip(skips).limit(page_size)
        total_records = mongo.command("collstats","single_cell_meta_country")['count']    

    # search type 2 - global search: search value is mongo raw query 
    elif search_type == "global":
        tmp = mongo.single_cell_meta_country.find(json.loads(search_params)).skip(skips).limit(page_size)
        total_records = mongo.single_cell_meta_country.count_documents(json.loads(search_params))
    # search type 3 - multi-column filter
    elif search_type == "column":
        tmp = mongo.single_cell_meta_country.find({"$and": search_params}).skip(skips).limit(page_size)
        total_records = mongo.single_cell_meta_country.count_documents({"$and": search_params}) 

    return tmp, total_records
            
# Pagination algorithm by ObjectId
from bson.objectid import ObjectId
def paginate_lastid(page_size, search_type, search_params, last_id=None):
        """Function returns `page_size` number of documents after last_id
        and the new last_id.
        """
        if last_id is None:
            # When it is first page
            print("When it is 1st page")
            tmp = mongo.single_cell_meta_country.find().limit(page_size)
            total_records = mongo.command("collstats","single_cell_meta_country")['count']   
        else:
            print("When it is 2nd and from on page")
             # search type 1 - no search: by default search value is empty ''
            if search_type == "default":
                
                tmp = mongo.single_cell_meta_country.find({'_id': {'$gt': ObjectId(last_id)}}).limit(page_size)
                total_records = mongo.command("collstats","single_cell_meta_country")['count']    

            # search type 2 - global search: search value is mongo raw query 
            elif search_type == "global":
                tmp = mongo.single_cell_meta_country.find(json.loads(search_params), {'_id': {'$gt': ObjectId(last_id)}}).limit(page_size)
                total_records = mongo.single_cell_meta_country.count_documents(json.loads(search_params))
            # search type 3 - multi-column filter
            elif search_type == "column":
                tmp = mongo.single_cell_meta_country.find({"$and": search_params}, {'_id': {'$gt': ObjectId(last_id)}}).limit(page_size)
                total_records = mongo.single_cell_meta_country.count_documents({"$and": search_params}) 

        # Get the data      
        data = [x for x in tmp]

        if not data:
            # No documents left
            return None, None

        # Since documents are naturally ordered with _id, last document will
        # have max id.
        last_id = data[-1]['_id']
        print(data[:2])
        print(last_id)
        print(total_records)

        # Return data and last_id
        return data, last_id, total_records           

# http://www.dotnetawesome.com/2015/12/implement-custom-server-side-filtering-jquery-datatables.html
# @login_required
@tasks.route('/api_db', methods=['GET', 'POST'])
def api_db():
    data = []
    if request.method == 'POST':
        draw = request.form['draw']
        row = int(request.form['start'])
        rowperpage = int(request.form['length'])
        page_no = int(row/rowperpage + 1)
        print(request.form)
        ## index page navigation graph url redirection
        if 'main' in request.args:
            search_value = request.args['main']
            print(request.args)
        else:
            search_value = request.form["search[value]"]

        print("draw: %s | row: %s | page size: %s | page num: %s | global search value: '%s'" % (draw, row, rowperpage, page_no, search_value))
        print("Checking user information")
        store_queryinfo(session)
        # session["user_id"] = str(current_user.id)
        session["user_id"] = shortuuid.uuid()
        print(session["user_id"])
        start = (page_no - 1)*rowperpage
        end = start + rowperpage
        map = {}
        for i in request.form:
            if ("[search][value]" in i) and (len(request.form[i]) != 0):
                column_value = request.form[i].split("|")
                if "0" in i:
                    search_column = "id"
                    map[search_column] = column_value
                elif "1" in i:
                    search_column = "meta_sample_id2"
                    map[search_column] = column_value
                elif "2" in i:
                    search_column = "meta_age_category"
                    map[search_column] = column_value
                elif "3" in i:
                    search_column = "level2"
                    map[search_column] = column_value
                elif "4" in i:
                    search_column = "meta_patient_id"
                    map[search_column] = column_value
                elif "5" in i:
                    search_column = "meta_dataset"
                    map[search_column] = column_value
                elif "6" in i:
                    search_column = "meta_severity"
                    map[search_column] = column_value
                else:
                    search_column = "pbmc.Country"
                    map[search_column] = column_value

        if search_value == '':
            # Pagination algorithm 
            # Calculate number of documents to skip
            tmp, total_records = paginate_skiplimit(rowperpage, page_no, "default", search_value) 

            # print("Using pagination by last_id algorithm")
            # if page_no == 1:
            #     tmp, last_id, total_records = paginate_lastid(rowperpage, "default", search_value, last_id=None)
            #     session["last_id"] = str(last_id)
            #     print(session["last_id"])
            # else:    
            #     tmp, last_id, total_records = paginate_lastid(rowperpage, "default", search_value, session["last_id"])
            #     session["last_id"] = str(last_id)

        else:
            print("global search value provided")
            session["query"] = json.loads(search_value)
            print(session["query"])
            # Pagination algorithm
            # Calculate number of documents to skip
            print("Using Pagination by mongodb skip-limit")
            tmp, total_records = paginate_skiplimit(rowperpage, page_no, "global", search_value) 

 

        if map:
            print("Column-specific (multi) search value provided")
            construct = query_builder(map)
            print("Saving construct to session query obj")
            session["query"] = construct
            print(session["query"])
            # Pagination algorithm
            # Calculate number of documents to skip
            tmp, total_records = paginate_skiplimit(rowperpage, page_no, "column", construct)
            
            checkpoint_time = time.time()
            print("finished --- %s seconds ---" % (time.time() - checkpoint_time))

        total_records_filter = total_records
        if total_records_filter == 0:
            print("return nothing")
            data.append({
                'id': "",
                'sample_id': "",
                'age': "",
                'prediction': "",
                'donor': "",
                'dataset': "",
                'status': "",
                'country':""
            })

        else:
            for r in tmp:
                data.append({
                        'id': r['id'],
                        'sample_id': r['meta_sample_id2'],
                        'age': r['meta_age_category'],
                        'prediction': r['level2'],
                        'donor': r['meta_patient_id'],
                        'dataset': r['meta_dataset'],
                        'status': r['meta_severity'],
                        'country': r['pbmc'][0]['Country']
                    })

        response = {
                'draw': draw,
                'iTotalRecords': total_records,
                'iTotalDisplayRecords': total_records_filter,
                'aaData': data,
        }

        return jsonify(response)


def get_field(field_name):
    key = mongo.single_cell_meta_country.distinct(field_name)
    print("%s has %d uniq fields" % (field_name, len(key)))
    return key



def get_study_field(field_name):
    key = mongo.pbmc_all_study_meta.distinct(field_name)
    print("%s has %d uniq fields" % (field_name, len(key)))
    return key

