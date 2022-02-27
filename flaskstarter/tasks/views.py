# -*- coding: utf-8 -*-

from flask import Blueprint, render_template, flash, redirect, url_for, send_file, request, jsonify
from flask_login import login_required, current_user

from ..extensions import db

from .forms import MyTaskForm
from .models import MyTaskModel
from flaskstarter.covid2k_meta import covid2k_metaModel
import csv

import pandas as pd
import numpy as np
import plotly
import plotly.express as px
import json

from pymongo import MongoClient
client = MongoClient('mongodb://localhost:27017/')
db = client.cov19atlas

tasks = Blueprint('tasks', __name__, url_prefix='/tasks')



# New view

@tasks.route('/table_view')
def table_view():
    col_values = get_col_values()
    return render_template('tasks/table_view.html', col_values=col_values)



import pandas as pd
from itertools import chain
import time
start_time = time.time()

print("--- %s seconds ---" % (time.time() - start_time))


# New code for pagination
print('regetting ids...')

#ids = [x["_id"] for x in list(db.single_cell_meta.find({}, {"_id": 1}))]
print('default ids')

@tasks.route('/filter_by_age',methods=['POST'])
def filter_by_age():
    query = {'age': { '$in': [52] }}
    ids = [x["_id"] for x in list(db.single_cell_meta.find(query, {"_id": 1}))]
    print('return new ids')
    return api_db()

data = []
# Write big file
def write_file_byid(path, towrite):
    print('writing data' + path)
    file = open(path + 'ids.csv', 'w+', newline='\n')
    print(towrite[0])
    data = [[r['id']] for r in towrite]
    print(data)
    with file:
        write = csv.writer(file)
        write.writerows(data)

# Download big file
@tasks.route('/download_file',methods=['POST'])
def download_file():
    return send_file('/tmp/flaskstarter-instance/' + 'ids.csv', as_attachment=True)

# set in-memory storage for collection of ids for meta data table display
collection = []
collection_s = []
@tasks.route('/api_db', methods=['GET', 'POST'])
@login_required
def api_db():
    print('testing db')

    data = []
    if request.method == 'POST':

        print('testing 1')
        #print(request)

        draw = request.form['draw']
        row = int(request.form['start'])
        rowperpage = int(request.form['length'])
        page_no = int(row/rowperpage + 1)
        searchValue = request.form["search[value]"]
        print(request.form)
        print(draw)
        print(row)
        print(rowperpage)
        print(page_no)
        print("print searchValue")
        print(searchValue)
        start = (page_no - 1)*rowperpage
        end = start + rowperpage

        if searchValue == '':
            if len(collection) == 0:
                ids = [x["_id"] for x in list(db.single_cell_meta.find({}, {"_id": 1}))]
                collection.extend(ids)
                tmp = db.single_cell_meta.find({'_id': {'$in': collection[start:end]}})
                totalRecords = len(collection)

            else:
                # refresh searchValue's stored ids when clicked "clear"
                collection_s.clear()
                tmp = db.single_cell_meta.find({'_id': {'$in': collection[start:end]}})
                totalRecords = len(collection)

        else:
            if len(collection_s) == 0:
                ids = [x["_id"] for x in list(db.single_cell_meta.find(json.loads(searchValue), {"_id": 1}))]
                collection_s.extend(ids)
                tmp = db.single_cell_meta.find({'_id': {'$in': collection_s[start:end]}})
                totalRecords = len(collection_s)
            else:
                tmp = db.single_cell_meta.find({'_id': {'$in': collection_s[start:end]}})
                totalRecords = len(collection_s)


        totalRecordwithFilter = totalRecords

        print('testing 2')
        for r in tmp:

            #print(r)
            data.append({
                    'id': r['id'],
                    'sample_id': r['sample_id'],
                    'age': r['age'],
                    'prediction': r['scClassify_prediction'],
                    'donor': r['donor'],
                    'dataset': r['dataset'],
                    'status': r['Status_on_day_collection_summary']
                })
            #print(data)
            response = {
                'draw': draw,
                'iTotalRecords': totalRecords,
                'iTotalDisplayRecords': totalRecordwithFilter,
                'aaData': data,
            }
            #print(response)

        if totalRecords != len(collection):
            towrite = list(db.single_cell_meta.find({'_id': {'$in': collection_s}}))
            print('writing ids to csv file')
            write_file_byid('/tmp/flaskstarter-instance/', towrite)

        return jsonify(response)



# Old code for small sample dataset before server-side processing is introduced 2022.2.27
# Old logic
@tasks.route('/my_tasks', methods=['GET', 'POST'])
@login_required
def my_tasks(condition=''):
    print('debug...')
    print('change condition...')
    print(condition)
    graphJSON = {}

    if not condition:
        #_all_tasks = covid2k_metaModel.query.limit(10).all()
        _all_tasks = db.single_cell_meta.find({}).limit(10)
        #print(list(meta))
        #print(len(list(_all_tasks)))
        print('show default')

    else:
        if isinstance(condition, str):
            if condition == 'all':
                _all_tasks = covid2k_metaModel.query.all()
                writefile('/tmp/flaskstarter-instance/', _all_tasks)
                print('show all')
            else:
                print('show' + condition)
                # _all_tasks = db.session.execute('SELECT * FROM covid2k_meta WHERE age LIKE 52')
                _all_tasks = covid2k_metaModel.query.filter(covid2k_metaModel.age.contains(condition)).all()
                writefile('/tmp/flaskstarter-instance/', _all_tasks)
                graphJSON = plot()
        elif isinstance(condition, list):
            _all_tasks = covid2k_metaModel.query.filter(covid2k_metaModel.donor.in_(condition)).all()
            writefile('/tmp/flaskstarter-instance/', _all_tasks)
            graphJSON = plot()
            print('show donors')


    print("reload...")
    print(condition)
    col_values = get_col_values()


    return render_template('tasks/my_tasks.html',
                           all_tasks=_all_tasks,
                           col_values=col_values,
                           graphJSON=graphJSON,
                           _active_tasks=True)

def writefile(path, towrite):
    print('writing data' + path)
    file = open(path + 'result.csv', 'w+', newline='\n')
    data = [[task.X] for task in towrite]
    with file:
        write = csv.writer(file)
        write.writerows(data)


@tasks.route('/showall',methods=['POST'])
def showall():
    return my_tasks('all')


@tasks.route('/age52',methods=['POST'])
def age_filter():
    return my_tasks('52')

@tasks.route('/download',methods=['POST'])
def download():
    plot()
    return send_file('/tmp/flaskstarter-instance/result.csv', as_attachment=True)


def get_col_values():
    #_col_values = covid2k_metaModel.query.with_entities(covid2k_metaModel.donor)
    donors = [c.donor for c in covid2k_metaModel.query.with_entities(covid2k_metaModel.donor).distinct()]
    print(len(donors))
    return donors

@tasks.route('/get_multiselect', methods=['POST'])
# uses list to store returned condition for my_tasks
def get_multiselect():
     selected_vals = request.form.getlist('multiselect')
     print(request.form)
     print(selected_vals)
     query = { 'donor': {'$in': selected_vals}}
     ids = [x["_id"] for x in list(db.single_cell_meta.find(query, {"_id": 1}))]
     #my_tasks(selected_vals)
     return table_view()

# to move outside of web app
def plot():
    path = '/tmp/flaskstarter-instance/'
    result = pd.read_csv(path + 'result.csv', header=None)
    df = pd.read_csv(path + 'cov192kaxis.csv', index_col=0)
    l = []
    for i in df.index:
        for j in result.values:
            if i == j:
                print(i)
                print(df.loc[i].values)
                l.append(df.loc[i].values)
    sln = np.stack(l)
    projections = sln
    fig = px.scatter(
        projections, x=0, y=1)
    fig.update_layout(
        autosize=False, width=900, height=600
    )
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return graphJSON


@tasks.route('/view_task/<id>', methods=['GET', 'POST'])
@login_required
def view_task(id):
    _task = MyTaskModel.query.filter_by(id=id, users_id=current_user.id).first()

    if not _task:
        flash('Oops! Something went wrong!.', 'danger')
        return redirect(url_for("tasks.my_tasks"))

    return render_template('tasks/view_task.html',
                           task=_task)


@tasks.route('/add_task', methods=['GET', 'POST'])
@login_required
def add_task():

    _task = MyTaskModel()

    _form = MyTaskForm()

    if _form.validate_on_submit():

        _task.users_id = current_user.id

        _form.populate_obj(_task)

        db.session.add(_task)
        db.session.commit()

        db.session.refresh(_task)
        flash('Your task is added successfully!', 'success')
        return redirect(url_for("tasks.my_tasks"))

    return render_template('tasks/add_task.html', form=_form, _active_tasks=True)


@tasks.route('/delete_task/<id>', methods=['GET', 'POST'])
@login_required
def delete_task(id):
    _task = MyTaskModel.query.filter_by(id=id, users_id=current_user.id).first()

    if not _task:
        flash('Oops! Something went wrong!.', 'danger')
        return redirect(url_for("tasks.my_tasks"))

    db.session.delete(_task)
    db.session.commit()

    flash('Your task is deleted successfully!', 'success')
    return redirect(url_for('tasks.my_tasks'))


@tasks.route('/edit_task/<id>', methods=['GET', 'POST'])
@login_required
def edit_task(id):
    _task = MyTaskModel.query.filter_by(id=id, users_id=current_user.id).first()

    if not _task:
        flash('Oops! Something went wrong!.', 'danger')
        return redirect(url_for("tasks.my_tasks"))

    _form = MyTaskForm(obj=_task)

    if _form.validate_on_submit():

        _task.users_id = current_user.id
        _form.populate_obj(_task)

        db.session.add(_task)
        db.session.commit()

        flash('Your task updated successfully!', 'success')
        return redirect(url_for("tasks.my_tasks"))

    return render_template('tasks/edit_task.html', form=_form, task=_task, _active_tasks=True)
