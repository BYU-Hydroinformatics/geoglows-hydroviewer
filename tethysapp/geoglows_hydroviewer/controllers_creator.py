import glob
import json
import os
import shutil
import urllib.parse
from zipfile import ZipFile

import geopandas as gpd
import geoserver.util
import jinja2
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from geoserver.catalog import Catalog
from tethys_sdk.gizmos import SelectInput
from tethys_sdk.permissions import login_required
import geomatics

from .app import HydroviewerTemplate as App
from .hydroviewer_creator_tools import get_project_directory

SHAPE_DIR = os.path.join(App.get_app_workspace().path, 'shapefiles')


@login_required()
def home(request):
    projects = []
    projects_path = os.path.join(App.get_app_workspace().path, 'projects')
    prjs = os.listdir(projects_path)
    prjs = [prj for prj in prjs if os.path.isdir(os.path.join(projects_path, prj))]
    for prj in prjs:
        if os.path.isdir(os.path.join(projects_path, prj)):
            projects.append((prj.replace('_', ' '), prj))
    if len(projects) == 0:
        projects_to_show = False
    else:
        projects_to_show = True

    projects = SelectInput(display_text='Existing Hydroviewer Projects',
                           name='project',
                           multiple=False,
                           options=projects)
    context = {
        'projects': projects,
        'projects_to_show': projects_to_show
    }

    return render(request, 'geoglows_hydroviewer/geoglows_hydroviewer_creator.html', context)


@login_required()
def add_new_project(request):
    project = request.GET.get('new_project_name', False)
    if not project:
        messages.error(request, 'Please provide a name for the new project')
        return redirect('..')
    project = str(project).replace(' ', '_')
    new_proj_dir = os.path.join(App.get_app_workspace().path, 'projects', project)
    try:
        os.mkdir(new_proj_dir)
        messages.success(request, 'Project Successfully Created')
        return redirect(f'../project_overview/?{urllib.parse.urlencode(dict(project=project))}')
    except:
        messages.error(request, 'Unable to create the project')
        return redirect('..')


@login_required()
def delete_existing_project(request):
    project = request.GET.get('project', False)
    if not project:
        messages.error(request, 'Project not found, please pick from list of projects or make a new one')
    else:
        try:
            shutil.rmtree(os.path.join(App.get_app_workspace().path, 'projects', project))
            messages.success(request, 'Project Deleted Successfully')
        except:
            messages.error(request, 'Failed to delete the project')
    return redirect('..')


@login_required()
def project_overview(request):
    project = request.GET.get('project', False)
    if not project:
        messages.error(request, 'Project not found, please pick from list of projects or make a new one')
        return redirect('..')
    proj_dir = get_project_directory(project)

    # check to see what data has been created (i.e. which of the steps have been completed)
    boundaries_created = os.path.exists(os.path.join(proj_dir, 'boundaries.json'))

    shapefiles_created = bool(
        os.path.exists(os.path.join(proj_dir, 'selected_catchment')) and
        os.path.exists(os.path.join(proj_dir, 'selected_drainageline'))
    )

    geoserver_configs = os.path.exists(os.path.join(proj_dir, 'geoserver_config.json'))
    if geoserver_configs:
        with open(os.path.join(proj_dir, 'geoserver_config.json')) as a:
            configs = json.loads(a.read())
        geoserver_url = configs['url']
        workspace = configs['workspace']
        drainagelines_layer = configs['dl_layer']
        catchment_layer = configs['ctch_layer']
    else:
        geoserver_url = ''
        workspace = ''
        drainagelines_layer = ''
        catchment_layer = ''

    context = {
        'project': project,
        'project_title': project.replace('_', ' '),

        'boundaries': boundaries_created,
        'boundariesJS': json.dumps(boundaries_created),

        'shapefiles': shapefiles_created,
        'shapefilesJS': json.dumps(shapefiles_created),

        'geoserver': geoserver_configs,
        'geoserverJS': json.dumps(geoserver_configs),
        'geoserver_url': geoserver_url,
        'workspace': workspace,
        'drainagelines_layer': drainagelines_layer,
        'catchment_layer': catchment_layer,
    }

    return render(request, 'geoglows_hydroviewer/creator_project_overview.html', context)


@login_required()
def draw_hydroviewer_boundaries(request):
    project = request.GET.get('project', False)
    if not project:
        messages.error(request, 'Unable to find this project')
        return redirect('../..')

    watersheds_select_input = SelectInput(
        display_text='Select A Watershed',
        name='watersheds_select_input',
        multiple=False,
        original=True,
        options=[['View All Watersheds', ''],
                 ["Islands", "islands-geoglows"],
                 ["Australia", "australia-geoglows"],
                 ["Japan", "japan-geoglows"],
                 ["East Asia", "east_asia-geoglows"],
                 ["South Asia", "south_asia-geoglows"],
                 ["Central Asia", "central_asia-geoglows"],
                 ["West Asia", "west_asia-geoglows"],
                 ["Middle East", "middle_east-geoglows"],
                 ["Europe", "europe-geoglows"],
                 ["Africa", "africa-geoglows"],
                 ["South America", "south_america-geoglows"],
                 ["Central America", "central_america-geoglows"],
                 ["North America", "north_america-geoglows"]],
        initial=''
    )

    context = {
        'project': project,
        'project_title': project.replace('_', ' '),
        'watersheds_select_input': watersheds_select_input,
        'geojson': bool(os.path.exists(os.path.join(get_project_directory(project), 'boundaries.json'))),
    }
    return render(request, 'geoglows_hydroviewer/creator_draw_hydroviewer_boundaries.html', context)


@login_required()
def save_drawn_boundaries(request):
    proj_dir = get_project_directory(request.POST['project'])

    geojson = request.POST.get('geojson', False)
    if geojson is not False:
        with open(os.path.join(proj_dir, 'boundaries.json'), 'w') as gj:
            gj.write(geojson)

    esri = request.POST.get('esri', False)
    if esri is not False:
        with open(os.path.join(proj_dir, 'boundaries.json'), 'w') as gj:
            gj.write(json.dumps(geomatics.data.get_livingatlas_geojson(esri)))

    gjson_file = gpd.read_file(os.path.join(proj_dir, 'boundaries.json'))
    gjson_file = gjson_file.to_crs("EPSG:3857")
    gjson_file.to_file(os.path.join(proj_dir, 'projected_selections'))
    return JsonResponse({'status': 'success'})


@login_required()
def choose_hydroviewer_boundaries(request):
    project = request.GET.get('project', False)
    if not project:
        messages.error(request, 'Unable to find this project')
        return redirect('../..')

    regions = SelectInput(
        display_text='Pick A World Region (ESRI Living Atlas)',
        name='regions',
        multiple=False,
        original=True,
        options=(
            ('None', ''),
            ('Antarctica', 'Antarctica'),
            ('Asiatic Russia', 'Asiatic Russia'),
            ('Australia/New Zealand', 'Australia/New Zealand'),
            ('Caribbean', 'Caribbean'),
            ('Central America', 'Central America'),
            ('Central Asia', 'Central Asia'),
            ('Eastern Africa', 'Eastern Africa'),
            ('Eastern Asia', 'Eastern Asia'),
            ('Eastern Europe', 'Eastern Europe'),
            ('European Russia', 'European Russia'),
            ('Melanesia', 'Melanesia'),
            ('Micronesia', 'Micronesia'),
            ('Middle Africa', 'Middle Africa'),
            ('Northern Africa', 'Northern Africa'),
            ('Northern America', 'Northern America'),
            ('Northern Europe', 'Northern Europe'),
            ('Polynesia', 'Polynesia'),
            ('South America', 'South America'),
            ('Southeastern Asia', 'Southeastern Asia'),
            ('Southern Africa', 'Southern Africa'),
            ('Southern Asia', 'Southern Asia'),
            ('Southern Europe', 'Southern Europe'),
            ('Western Africa', 'Western Africa'),
            ('Western Asia', 'Western Asia'),
            ('Western Europe', 'Western Europe'),)
    )

    context = {
        'project': project,
        'project_title': project.replace('_', ' '),
        'regions': regions,
        'geojson': bool(os.path.exists(os.path.join(get_project_directory(project), 'boundaries.json'))),
    }
    return render(request, 'geoglows_hydroviewer/creator_choose_hydroviewer_boundaries.html', context)


@login_required()
def retrieve_hydroviewer_boundaries(request):
    proj_dir = get_project_directory(request.GET['project'])
    with open(os.path.join(proj_dir, 'boundaries.json'), 'r') as geojson:
        return JsonResponse(json.load(geojson))


@login_required()
def upload_boundary_shapefile(request):
    project = request.POST.get('project', False)
    if not project:
        return JsonResponse({'status': 'error', 'error': 'project not found'})
    proj_dir = get_project_directory(project)

    # make the projected selections folder
    tmp_dir = os.path.join(proj_dir, 'projected_selections')
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.mkdir(tmp_dir)

    # save the uploaded shapefile to that folder
    files = request.FILES.getlist('files')
    for file in files:
        file_name = 'projected_selections' + os.path.splitext(file.name)[-1]
        with open(os.path.join(tmp_dir, file_name), 'wb') as dst:
            for chunk in file.chunks():
                dst.write(chunk)

    # read the uploaded shapefile with geopandas and save it to selections.geojson
    boundaries_gdf = gpd.read_file(os.path.join(tmp_dir, 'projected_selections.shp'))
    boundaries_gdf = boundaries_gdf.to_crs("EPSG:3857")
    boundaries_gdf.to_file(os.path.join(tmp_dir, 'projected_selections.shp'))
    boundaries_gdf = boundaries_gdf.to_crs("EPSG:4326")
    boundaries_gdf.to_file(os.path.join(proj_dir, "boundaries.json"), driver='GeoJSON')

    return JsonResponse({'status': 'success'})


@login_required()
def geoprocess_hydroviewer_idregion(request):
    project = request.GET.get('project', False)
    if not project:
        raise FileNotFoundError('project directory not found')
    proj_dir = get_project_directory(project)
    gjson_gdf = gpd.read_file(os.path.join(proj_dir, 'projected_selections', 'projected_selections.shp'))

    for region_zip in glob.glob(os.path.join(SHAPE_DIR, '*-boundary.zip')):
        region_name = os.path.splitext(os.path.basename(region_zip))[0]
        boundary_gdf = gpd.read_file("zip:///" + os.path.join(region_zip, region_name + '.shp'))
        if gjson_gdf.intersects(boundary_gdf)[0]:
            return JsonResponse({'region': region_name})
    return JsonResponse({'error': 'unable to find a region'}), 422


@login_required()
def geoprocess_hydroviewer_clip(request):
    project = request.GET.get('project', False)
    region_name = request.GET.get('region', False)
    if not project:
        return JsonResponse({'error': 'unable to find the project'})
    proj_dir = get_project_directory(project)

    catch_folder = os.path.join(proj_dir, 'selected_catchment')
    dl_folder = os.path.join(proj_dir, 'selected_drainageline')

    if request.GET.get('shapefile', False) == 'drainageline':
        if os.path.exists(dl_folder):
            shutil.rmtree(dl_folder)
        os.mkdir(dl_folder)

        gjson_gdf = gpd.read_file(os.path.join(proj_dir, 'projected_selections', 'projected_selections.shp'))
        dl_name = region_name.replace('boundary', 'drainageline')
        dl_path = os.path.join(SHAPE_DIR, dl_name + '.zip', dl_name + '.shp')
        dl_gdf = gpd.read_file("zip:///" + dl_path)

        dl_point = dl_gdf.representative_point()
        dl_point_clip = gpd.clip(dl_point, gjson_gdf)
        dl_boo_list = dl_point_clip.within(dl_gdf)
        dl_select = dl_gdf[dl_boo_list]
        dl_select.to_file(os.path.join(dl_folder, 'drainageline_select.shp'))
        return JsonResponse({'status': 'success'})

    elif request.GET.get('shapefile', False) == 'catchment':
        if os.path.exists(catch_folder):
            shutil.rmtree(catch_folder)
        os.mkdir(catch_folder)

        dl_select = gpd.read_file(os.path.join(dl_folder, 'drainageline_select.shp'))
        catch_name = region_name.replace('boundary', 'catchment')
        catch_path = os.path.join(SHAPE_DIR, catch_name + '.zip', catch_name + '.shp')
        catch_gdf = gpd.read_file("zip:///" + catch_path)
        catch_gdf = catch_gdf.loc[catch_gdf['COMID'].isin(dl_select['COMID'].to_list())]
        catch_gdf.to_file(os.path.join(catch_folder, 'catchment_select.shp'))
        return JsonResponse({'status': 'success'})

    else:
        raise ValueError('illegal shapefile type specified')


@login_required()
def shapefile_export_geoserver(request):
    project = request.GET.get('project', False)
    url = request.GET.get('gs_url')
    username = request.GET.get('gs_username', 'admin')
    password = request.GET.get('gs_password', 'geoserver')
    workspace_name = request.GET.get('workspace', 'geoglows_hydroviewer_creator')
    dl_name = request.GET.get('dl_name', 'drainagelines')
    ct_name = request.GET.get('ct_name', 'catchments')
    if not project:
        return JsonResponse({'error': 'unable to find the project'})
    proj_dir = get_project_directory(project)

    try:
        cat = Catalog(url, username=username, password=password)

        # identify the geoserver stores
        workspace = cat.get_workspace(workspace_name)

        # todo verify that the workspace exists (script will complete w/o uploading files if workspace doesn't exist)
        # todo what if the catchments are too large -- common problem preventing shapefile upload

        try:
            # create geoserver store and upload the catchments
            shapefile_plus_sidecars = geoserver.util.shapefile_and_friends(
                os.path.join(proj_dir, 'selected_catchment', 'catchment_select'))
            cat.create_featurestore(ct_name, workspace=workspace, data=shapefile_plus_sidecars, overwrite=True)
        except Exception as e:
            print('failed to upload catchments')
            print(e)

        try:
            # create geoserver store and upload the drainagelines
            shapefile_plus_sidecars = geoserver.util.shapefile_and_friends(
                os.path.join(proj_dir, 'selected_drainageline', 'drainageline_select'))
            cat.create_featurestore(dl_name, workspace=workspace, data=shapefile_plus_sidecars, overwrite=True)
        except Exception as e:
            print('failed to upload drainagelines')
            print(e)

        # geoserver_configs keys to be added to geoserver_configs dictionary
        geoserver_configs = {
            'url': url.replace('/rest/', '/wms'),
            'workspace': workspace_name,
            'dl_layer': dl_name,
            'ctch_layer': ct_name,
        }

        with open(os.path.join(proj_dir, 'geoserver_config.json'), 'w') as configfile:
            configfile.write(json.dumps(geoserver_configs))
    except Exception as e:
        print(e)
        return JsonResponse({'status': 'failed'})

    return JsonResponse({'status': 'success'})


@login_required()
def shapefile_export_zipfile(request):
    project = request.GET.get('project', False)
    if not project:
        return JsonResponse({'error': 'unable to find the project'})
    proj_dir = get_project_directory(project)
    zip_path = os.path.join(proj_dir, 'hydroviewer_shapefiles.zip')

    # if there is already a zip file, serve it for download
    if os.path.exists(zip_path):
        zip_file = open(zip_path, 'rb')
        response = HttpResponse(zip_file, content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename="hydroviewer_shapefiles.zip"'
        return response

    catchment_shapefile = os.path.join(proj_dir, 'selected_catchment', 'catchment_select.shp')
    drainageline_shapefile = os.path.join(proj_dir, 'selected_drainageline', 'drainageline_select.shp')
    if not os.path.exists(catchment_shapefile):
        raise FileNotFoundError('selected catchment shapefile does not exist')
    if not os.path.exists(drainageline_shapefile):
        raise FileNotFoundError('selected drainageline shapefile does not exist')

    try:
        with ZipFile(zip_path, 'w') as zipfile:
            catchment_components = glob.glob(os.path.join(proj_dir, 'selected_catchment', 'catchment_select.*'))
            for component in catchment_components:
                zipfile.write(component, arcname=os.path.join('selected_catchment', os.path.basename(component)))
            dl_components = glob.glob(os.path.join(proj_dir, 'selected_drainageline', 'drainageline_select.*'))
            for component in dl_components:
                zipfile.write(component, arcname=os.path.join('selected_drainageline', os.path.basename(component)))
    except Exception as e:
        shutil.rmtree(zip_path)
        raise e

    zip_file = open(zip_path, 'rb')
    response = HttpResponse(zip_file.read(), content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="hydroviewer_shapefiles.zip"'
    return response


@login_required()
def project_export_html(request):
    project = request.GET.get('project', False)
    if not project:
        return JsonResponse({'error': 'unable to find the project'})
    proj_dir = get_project_directory(project)
    html_path = os.path.join(proj_dir, 'hydroviewer.html')

    with open(os.path.join(proj_dir, 'geoserver_config.json')) as configfile:
        geoserver_configs = json.loads(configfile.read())
    with open(os.path.join(proj_dir, 'boundaries.json')) as bndsgj:
        boundaries_json = json.loads(bndsgj.read())
    with open(os.path.join(App.get_app_workspace().path, 'hydroviewer_interactive.html'), 'r') as template:
        with open(html_path, 'w') as hydrohtml:
            hydrohtml.write(
                jinja2.Template(template.read()).render(
                    title=project.replace('_', ' '),
                    api_endpoint='https://tethys2.byu.edu/localsptapi/api/',
                    geoserver_wms_url=geoserver_configs['url'],
                    workspace=geoserver_configs['workspace'],
                    catchment_layer=geoserver_configs['ctch_layer'],
                    drainage_layer=geoserver_configs['dl_layer'],
                    boundaries_json=json.dumps(boundaries_json),
                )
            )

    with open(html_path, 'r') as htmlfile:
        response = HttpResponse(htmlfile, content_type='text/html')
        response['Content-Disposition'] = f'attachment; filename="{project}_hydroviewer.html"'
        return response