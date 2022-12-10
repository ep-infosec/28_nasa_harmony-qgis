from datetime import datetime
from time import sleep
from pathlib import Path
import json
import http.client as http_client
import logging
import tempfile
import os
import requests
import traceback

from qgis.core import Qgis, QgsApplication, QgsProject, QgsProcessingFeedback, QgsProcessingContext, QgsSettings, QgsTaskManager, QgsTask, QgsProject, QgsSettings, QgsVectorLayer, QgsVectorFileWriter, QgsCoordinateTransformContext, QgsRasterLayer, QgsMessageLog
from qgis.PyQt import QtWidgets

# Session accessible by callers
session = requests.session()

# keep track of progress so we can reset when QGIS wipes out the progress bar after each background
# task completes
total_progress = 0

def debug_http():
  """Adds debugging output to HTTP requests to show redirects, headers, etc
  """
  http_client.HTTPConnection.debuglevel = 1
  logging.basicConfig()
  logging.getLogger().setLevel(logging.DEBUG)
  requests_log = logging.getLogger("requests.packages.urllib3")
  requests_log.setLevel(logging.DEBUG)
  requests_log.propagate = True

def request(*args, **kwargs):
  """Thin wrapper around requests.Request, logging URL sent and Content-Type received

  See https://requests.readthedocs.io/en/master/api/#requests.Request for args

  Returns:
      requests.Response -- The response to the request
  """
  req = requests.Request(*args, **kwargs)
  prepped = session.prepare_request(req)

  response = session.send(prepped)
  return response

def get(*args, **kwargs):
  """Performs a GET request using the request wrapper

  See https://requests.readthedocs.io/en/master/api/#requests.Request for args

  Returns:
      requests.Response -- The response to the request
  """
  return request('GET', *args, **kwargs)

def post(*args, **kwargs):
  """Performs a POST request using the request wrapper

  See https://requests.readthedocs.io/en/master/api/#requests.Request for args

  Returns:
      requests.Response -- The response to the request
  """
  return request('POST', *args, **kwargs)

def get_data_urls(response):
  """Returns the data URLs in an async response

  Arguments:
      response {response.Response} -- The async job response

  Returns:
      string[] -- An array of URLs for data links
  """
  return [link['href'] for link in response.json()['links'] if link.get('rel', 'data') == 'data']

def download_image(response, layerName):
  settings = QgsSettings()
  directory = settings.value("harmony_qgis/download_dir") or tempfile.gettempdir()
  Path(directory).mkdir(parents=True, exist_ok=True)
  filename = directory + os.path.sep + 'harmony_output_image' + layerName + '.tif'
  with open(filename, 'wb') as fd:
    for chunk in response.iter_content(chunk_size=128):
      fd.write(chunk)
  return filename

def pollResults(task, iface, response, link_count):
  global total_progress
  body = response.json()
  links = get_data_urls(response)
  new_links = links[slice(link_count, None)]
  new_layers = []
  link_count = len(links)

  if task:
    task.setProgress(total_progress)

  progress = int(body['progress'])

  for link in new_links:
      if link.startswith('http'):
        lastSlash = link.rindex('/')
        layerName = link[lastSlash + 1:]
        extensionIndex = layerName.rindex('.')
        if extensionIndex >= 0:
          layerName = layerName[0:extensionIndex]
        fileName = download_image(get(link), layerName)
        new_layers.append((layerName, fileName))
  if task:
    task.setProgress(progress)
  if progress == 100:
    total_progress = 0
  else:
    total_progress = progress

  status = body['status']
  if status not in ['successful', 'failed']:
    sleep(1)
    response = requests.get(response.url)
  else:
    status = 'done'
  return { 'iface': iface, 'response': response, 'status': status, 'link_count': link_count, 'new_layers': new_layers }

def completed(exception, result=None):
  """Called when a worker tasks completes
    Arguments:
      exception {Exception} -- if an error occurs
      result {} - the response from  the worker task
  """
  if exception is None:
    iface = result['iface']
    if result is None:
      status = 'Completed with no error and no result'
      iface.mainWindow().statusBar().showMessage(status)
    else:
      status = result['status']
      link_count = result['link_count']
      new_layers = result['new_layers']
      new_iface_layers = []
      for layerName, fileName in new_layers:
        layer = iface.addRasterLayer(fileName, layerName)
        if not layer or not layer.isValid():
          iface.messageBar().pushMessage("Error", "Failed to create layer {}".format(layerName), level=Qgis.Critical, duration=0)

      if status != 'done':
        response = result['response']
        globals()['task'] = QgsTask.fromFunction('Worker', pollResults, on_finished=completed, iface=iface, response=response, link_count=link_count)
        QgsApplication.taskManager().addTask(globals()['task'])
      else:
        status = "Download complete - {} new layers created".format(link_count)
        iface.mainWindow().statusBar().showMessage(status)
  else:
    iface.messageBar().pushMessage("Error", 'Error while processing downloads', level=Qgis.Critical, duration=0)

def handleAsyncResponse(iface, response, background):
  iface.mainWindow().statusBar().showMessage(u'Downloading Harmony results')
  
  # background download tasks when not running tests
  if background:
    globals()['task'] = QgsTask.fromFunction('Worker', pollResults, on_finished=completed, iface=iface, response=response, link_count=0)
    QgsApplication.taskManager().addTask(globals()['task'])
  else:
    result = pollResults(None, iface, response, 0)
    while result['status'] != 'done':
      result = pollResults(None, iface, result['response'], result['link_count'])
    response = result['response']
    for link in get_data_urls(response):
      if link.startswith('http'):
        lastSlash = link.rindex('/')
        layerName = link[lastSlash + 1:]
        extensionIndex = layerName.rindex('.')
        if extensionIndex >= 0:
          layerName = layerName[0:extensionIndex]
        fileName = download_image(get(link), layerName)
        layer = iface.addRasterLayer(fileName, layerName)
        if not layer or not layer.isValid():
          iface.messageBar().pushMessage("Error", "Failed to create layer {}".format(layerName), level=Qgis.Critical, duration=0)

def handleSyncResponse(iface, response, layerName, variable):
  with open(tempfile.gettempdir() + os.path.sep + 'harmony_output_image.tif', 'wb') as fd:
    for chunk in response.iter_content(chunk_size=128):
      fd.write(chunk)

  iface.addRasterLayer(tempfile.gettempdir() + os.path.sep + 'harmony_output_image.tif', layerName + '-' + variable)

def handleErrorResponse(iface, response):
  statusCode = response.status_code
  description = response.json()['description']
  # handle special case
  if description == "Error: Cannot set property 'user' of undefined":
    description = 'Invalid Harmony API version'
  iface.messageBar().pushMessage("", description, level=Qgis.Critical, duration=0)
  
def handleHarmonyResponse(iface, response, layerName, variable, background = True):
  if response.status_code > 299:
    handleErrorResponse(iface, response)
    return

  content_type = response.headers['Content-Type']
  message = 'Content-type is: ' + content_type

  if content_type == 'application/json; charset=utf-8':
    handleAsyncResponse(iface, response, background)
  else:
    handleSyncResponse(iface, response, layerName, variable)
