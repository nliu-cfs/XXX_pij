# -*- coding: utf-8 -*-
"""
Created on Mon Aug  7 11:47:13 2023

@author: nliu

Step 1. input Burn-P3 results, check coordinate system
step 2. create hexagon grids based on the boundaries set by geometry of fireshed files
Step 3. 

"""

import geopandas as gpd
from shapely.geometry import Polygon, Point, LineString
import pandas as pd
import warnings
warnings.filterwarnings("ignore")
import math
from tqdm import tqdm

def create_hexagon(size, x, y):
    """
    Create a hexagon centered on (x, y)
    :param l: length of the hexagon's edge
    :param x: x-coordinate of the hexagon's center
    :param y: y-coordinate of the hexagon's center
    :return: The polygon containing the hexagon's coordinates
    """
    l = 3**0.25 * math.sqrt(2 * size / 9)

    c = [[x + math.cos(math.radians(angle)) * l, y + math.sin(math.radians(angle)) * l] for angle in range(0, 360, 60)]
    return Polygon(c)

def create_hexgrid(size, xmin, ymin, xmax, ymax):
    """
    Parameters
    ----------
    size : TYPE float
        area of intended hexagon in squaremeters.
    xmin,ymin,xmax,ymax : TYPE float
        canvas boundaries for hexagon grids.
   
    Returns
    -------
    pologon containing hexagon's coordinates.
    """
    grid = []
    
    side = 3**0.25 * math.sqrt(2 * size / 9)
    v_step = math.sqrt(3) * side
    h_step = 1.5 * side


    h_skip = math.ceil(xmin / h_step) - 1
    h_start = h_skip * h_step

    v_skip = math.ceil(ymin / v_step) - 1
    v_start = v_skip * v_step

    h_end = xmax + h_step
    v_end = ymax + v_step

    if v_start - (v_step / 2.0) < ymin:
        v_start_array = [v_start + (v_step / 2.0), v_start]
    else:
        v_start_array = [v_start - (v_step / 2.0), v_start]

    v_start_idx = int(abs(h_skip) % 2)

    c_x = h_start
    c_y = v_start_array[v_start_idx]
    v_start_idx = (v_start_idx + 1) % 2
    while c_x < h_end:
        while c_y < v_end:
            grid.append((c_x, c_y))
            c_y += v_step
        c_x += h_step
        c_y = v_start_array[v_start_idx]
        v_start_idx = (v_start_idx + 1) % 2

    return grid

import os
os.chdir(r'C:\Users\nliu\Documents\014 Potential\methodPaper\pycode') 
 
#### read in BurnP-3 output fire shapefile 
fire = gpd.read_file('testBurnPFF_1909.shp', encoding="utf-8", driver = 'ESRI Shapefile')
fire = fire[['fire', 'iteration', 'geometry']]

#### specify coordinate system of the fire shape dat
prj = 'EPSG:3400'   # this is the one for example data set
fire = fire.to_crs(prj)

#### read in BurnP-3 output ignition point csv file
ignPt = 'testBurnP_1909_Stats.csv'
points = pd.read_csv(ignPt)
points['geometry'] = [Point(xy) for xy in zip(points['x_coord'], points['y_coord'])]
# note: make sure ignition points and fire shape are of the same projection, below it directly set by prj
points = gpd.GeoDataFrame(points, crs = prj, geometry = points['geometry'] )
points = points[['fire', 'iteration', 'geometry']]


######## generate hexagon grids that covers all fire shapes ########
xmin,ymin,xmax,ymax =  fire.total_bounds

# specify intended size of hexes
size = 1000000
diameter = 3**0.25 * math.sqrt(2 * size / 9) *2

hex_centers = create_hexgrid(size, xmin, ymin, xmax, ymax)
nodes = gpd.GeoDataFrame({'geometry': hex_centers})

hexagon = [create_hexagon(size, center[0], center[1]) for center in hex_centers] 
hexagon = gpd.GeoDataFrame({'geometry':hexagon})
hexagon['Node_ID'] = hexagon.index + 1
hexagon.crs = fire.crs

### create node shapefile to get centroid geometry of hexagons
nodes = hexagon.copy()
nodes['centroid'] = nodes.geometry.centroid
nodes = nodes[['Node_ID', 'centroid']]
nodes.columns = ['Node_ID', 'geometry']
nodes = nodes.set_geometry('geometry')

# nodes.to_file('nodes.shp', driver = 'ESRI Shapefile')

print('------starting spatial joins------')
fireEvents = pd.DataFrame()
# threshold = 0  #0.025 * 10**6 #0.025

#### do we need to loop through iterations too?
for i in tqdm(points['fire']):
    try:
        fire_i = fire.loc[fire['fire'] == i]
        fire_ni = gpd.overlay(fire_i, hexagon, how = 'intersection')
        # ####  adding threshold for fire range > 2.5%
        # fire_ni['areaFire'] = fire_ni.geometry.area
        # fire_ni = fire_ni.loc[fire_ni['areaFire'] > threshold]
                
        pts_i = points.loc[points['fire'] == i]
        pts_ni = gpd.sjoin(pts_i, hexagon, how = 'inner', predicate = 'within')
        pts_ni = pts_ni[['fire', 'Node_ID']]
        
        dfTemp = fire_ni.merge(pts_ni, on = 'fire', how = 'left')
        dfTemp = dfTemp.drop(dfTemp[dfTemp['Node_ID_x'] == dfTemp['Node_ID_y']].index)
        dfTemp.drop(labels = ['geometry'], axis = 1, inplace = True)
        fireEvents = pd.concat([fireEvents, dfTemp], sort = True)
    except:
        print(f'spatial join does not apply to fire #{i}')  
        
fireEvents = fireEvents.reset_index(drop = True)
fireEvents.drop(fireEvents[fireEvents['Node_ID_y'].isna()].index, inplace = True)                    

fireEvents['Node_ID_x'] = fireEvents['Node_ID_x'].astype(int)
fireEvents['Node_ID_y'] = fireEvents['Node_ID_y'].astype(int)

fireEvents.columns = ['Node_ID_x', 'Node_ID_y', 'fire', 'iteration']
###### output file  #######
fireEvents.to_csv('burningEvent_all.txt', index = False, sep = '\t', header = True)
###########################################################
############## input spatial join data#####################
fireEvents = pd.read_csv(r'burningEvent_all.txt', sep = '\t', header = 0)
fireEvents00 = fireEvents.copy()

fireCounts = fireEvents.groupby(['Node_ID_x', 'Node_ID_y'])[['fire']].count()
fireCounts.reset_index(inplace = True)
fireCounts = fireCounts.drop(fireCounts[fireCounts['Node_ID_x'] == fireCounts['Node_ID_y']].index)

fireCounts.to_csv('pij_num_all.txt', sep = '\t', index = False, header = 0)

###### plot pij map



##### generate arcs shapefile

fireCounts = nodes.merge(fireCounts, left_on = 'Node_ID', right_on = 'Node_ID_y', how = 'right')
fireCounts = fireCounts.drop(labels = 'Node_ID', axis = 1)
fireCounts = fireCounts.merge(nodes, left_on = 'Node_ID_x', right_on = 'Node_ID', how = 'left')
fireCounts = fireCounts.drop(labels = 'Node_ID', axis = 1)

connect = [LineString(xy) for xy in zip(fireCounts['geometry_x'], fireCounts['geometry_y'])]
fireCounts.drop(labels = ['geometry_x', 'geometry_y'], axis = 1, inplace = True)
connect = gpd.GeoDataFrame(fireCounts, crs = fire.crs, geometry = connect )
connect = connect.rename(columns = {'Node_ID_y': 'ignPt', 'Node_ID_x': 'spreadPt', 'fire': 'counts'})
connect.sort_values(by = 'counts', inplace = True)
connect.reset_index(drop = True, inplace = True)

connect.to_file(filename = 'firecounts.shp', driver = 'ESRI Shapefile')



