import pickle
import os
import pandas as pd
import networkx as nx
import osmnx as ox
import overpy
import shapely.geometry as geometry
from shapely.ops import linemerge, unary_union, polygonize
import osgeo
from osgeo import ogr
import geopandas as gpd
import fiona
from time import time
import mapclassify
import geoplot
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor

pip install mapclassify
pip install geoplot

name = 'Philadelphia, Pennsylvania, USA'
north = 39.9811
south = 39.9228
east = -75.1417
west = -75.2309
query = """[out:json][timeout:25];
rel(188022);
out body;
>;
out skel qt; """
api = overpy.Overpass()
result = api.query(query)

lss = [] #convert ways to linstrings

for ii_w,way in enumerate(result.ways):
    ls_coords = []

    for node in way.nodes:
        ls_coords.append((node.lon,node.lat)) # create a list of node coordinates

    lss.append(geometry.LineString(ls_coords)) # create a LineString from coords


merged = linemerge([*lss]) # merge LineStrings
borders = unary_union(merged) # linestrings to a MultiLineString
polygons = list(polygonize(borders))
philly = geometry.MultiPolygon(polygons)


ox.settings.useful_tags_path = ['route','lcn','segregated','rcn','rcn_ref','lcn_ref','bridge','tunnel','oneway','lanes','highway','maxspeed','service','access','area','landuse','width','est_width','junction','cycleway:right','cycleway:left','surface','cycleway','cycleway:both']


def load_graph(name,north=None,south=None,east=None,west=None):
    pickle_path = './' +name+'.gpickle'
    if os.path.exists(pickle_path):
        graph = nx.read_gpickle(pickle_path)
    else:
        graph = ox.graph_from_place(name, network_type='bike',simplify=True)
        nx.write_gpickel(G, pickle_path)
    if north is not None:
        return ox.truncate.truncate_graph_bbox(graph,north,south,east,west)
    return graph


def load_polygon(name,query):
    pass
polygon = philly

def load_crashes():
    df_crash = pd.read_csv('./RawData/PHILADELPHIA_1999/CRASH_1999_Philadelphia.csv')
    for i in range(18):
        s = str(i)
        if i < 10:
            s = '0' + str(s)
        path = './RawData/PHILADELPHIA_20' + s +'/CRASH_20'+ s + '_Philadelphia.csv'
        df_to_merge = pd.read_csv(path)
        df_crash = pd.concat([df_crash,df_to_merge])
    return df_crash

def load_traffic():
    return pd.read_csv('./RawData/DVRPC_Bicycle_Counts.csv')

def clean_crashes(df,polygon):
    an = df.copy()
    an = an[an['BICYCLE_COUNT'] > 0]
    in_location = an.apply(lambda r: polygon.contains(geometry.Point(r['DEC_LONG'], r['DEC_LAT'])),axis=1)
    an = an[in_location]
    if north is not None:
        an = an[an['DEC_LONG'] < east]
        an = an[an['DEC_LONG'] > west]
        an = an[an['DEC_LAT'] < north]
        an = an[an['DEC_LAT'] > south]
    return an

def clean_traffic(df,polygon):
    an = df.copy()
    if north is not None:
        an = an[an['X'] < east]
        an = an[an['X'] > west]
        an = an[an['Y'] < north]
        an = an[an['Y'] > south]
    in_location = an.apply(lambda r: polygon.contains(geometry.Point(r['X'], r['Y'])),axis=1)
    an = an[in_location]
    return an


def exploder_one_hot(df,column_name_list):
    to_concat = [df.copy()]
    for col in column_name_list:
        to_concat.append(df[col].apply(lambda x: [x]).str.join('|').str.get_dummies().add_prefix(col + ":"))
        #return df[col].apply(lambda x: [x]).str.join('|').str.get_dummies()
    return pd.concat(to_concat,axis=1).drop(column_name_list,axis=1)

def edge_featurizer(df,column_name_list):
    an = exploder_one_hot(df,column_name_list)
    an['x'] = an.apply(lambda r: r.geometry.centroid.x, axis=1)
    an['y'] = an.apply(lambda r: r.geometry.centroid.y, axis=1)
    return an





def traffic_func(r,G):
    return ox.get_nearest_edge(G,(r['Y'],r['X']),return_geom = True,return_dist = True)


def give_each_traffic_an_edge(df_traffic,G):
    df_traffic['closest_edge'] = df_traffic.apply(lambda x : traffic_func(x,G),axis=1)

def crash_func(r,G):
    return ox.get_nearest_node(G,(r['DEC_LAT'],r['DEC_LONG']))

def tag_crashes(df_crash,G,df_nodes,prefix=''):
    df_crash['nearest_node'] = df_crash.apply(lambda x: crash_func(x,G),axis=1)

def number_of_crashes_at_a_node(df_crash,G,df_nodes,prefix=''):
    s_counts = df_crash['nearest_node'].value_counts()
    df_nodes['number_of_accidents' + prefix] = df_nodes.apply(lambda x: s_counts[x['osmid']] if x['osmid'] in s_counts.index else 0,axis=1)


def beta_values(mean,std):
    alpha = ((1-mean)/std/std -(1 / mean))* mean * mean
    beta = alpha*(1/mean - 1)
    return alpha,beta



column_name_list = ['highway', 'surface', 'segregated', 'service', 'cycleway', 'lanes', 'cycleway:right', 'maxspeed', 'cycleway:left', 'access', 'lcn',
        'tunnel', 'bridge', 'rcn_ref', 'width', 'junction']


philly

## loading data
df_traffic = clean_traffic(load_traffic(),philly)
df_crashes = clean_crashes(load_crashes(),philly)
G = load_graph(name,north,south,east,west)
G_undirected = G.to_undirected()
df_nodes = ox.graph_to_gdfs(G_undirected,edges=False)
df_edges = ox.graph_to_gdfs(G_undirected,nodes=False)
df_edges_with_features = edge_featurizer(df_edges,column_name_list)
df_edges_with_features['oneway'] = df_edges_with_features['oneway']*1.0


# give each traffic an edge, take a while (10min)
t = time()
give_each_traffic_an_edge(df_traffic,G_undirected)
print(time()-t)


df_traffic['closest_edge']
df_traffic['closest_edge_poly'] = df_traffic.apply(lambda x: x['closest_edge'][3], axis=1)
df_traffic['u'] = df_traffic.apply(lambda x: x['closest_edge'][0], axis=1)
df_traffic['v'] = df_traffic.apply(lambda x: x['closest_edge'][1], axis=1)
gdf_traffic = gpd.GeoSeries(df_traffic['closest_edge_poly'])

df_traffic.head(1)
df_traffic.columns

df_traffic_grouped = df_traffic.groupby(['u','v','setdate']).agg({'road':'first','X':'first','Y':'first', 'setyear':'first', 'aadb':'sum', 'closest_edge':'first', 'closest_edge_poly':'first'})
df_traffic_grouped['key'] = 0
df_traffic_grouped = df_traffic_grouped.reset_index()

df_traffic_grouped_with_features = pd.merge(df_traffic_grouped,df_edges_with_features, how = 'left', on=['u','v','key'])
df_traffic_grouped_with_features.columns
df_traffic_grouped_with_features.head()
df_traffic_grouped_with_features = df_traffic_grouped_with_features.drop(['road','X','Y','closest_edge','u','v','setdate','closest_edge_poly'],axis=1)
df_traffic_grouped_with_features.columns

df_traffic_grouped_with_features_altered = df_traffic_grouped_with_features[df_traffic_grouped_with_features['setyear'] < 2019]
df_traffic_grouped_with_features_altered['aadb'].hist()

df_traffic_grouped_with_features_altered.groupby('setyear')['aadb'].mean()[2010]

def scale_traffic_for_year_2017(df_traffic):
    s = df_traffic.groupby('setyear')['aadb'].mean()
    amt = s[2017]
    df_traffic['aadb_year_adjusted'] = df_traffic.apply(lambda x: x['aadb']*amt/s[x['setyear']],axis=1)

scale_traffic_for_year_2017(df_traffic_grouped_with_features_altered)



traffic_x = df_traffic_grouped_with_features_altered.drop(['key','aadb','osmid','geometry'],axis=1)
traffic_y = df_traffic_grouped_with_features_altered[['aadb','setyear']]


traffic_x_train = traffic_x[traffic_x['setyear'] != 2017]
traffic_y_train = traffic_y[traffic_y['setyear'] != 2017]

traffic_x_train.columns
#traffic_y_train = traffic_y_train.drop('setyear',axis=1)
#traffic_x_train = traffic_x_train.drop('aadb',axis=1)
traffic_x_train = traffic_x_train.sort_index(axis=1)


np.ravel(traffic_y_train.head())

## models for traffic
#reg = LinearRegression().fit(traffic_x_train.sort_index(axis=1),traffic_y_train)
regr = RandomForestRegressor(max_depth=5, random_state=0)
regr.fit(traffic_x_train,np.ravel(traffic_y_train['aadb']))
np.array(traffic_y_train['aadb'])/regr.predict(traffic_x_train.sort_index(axis=1))

#df_edges_with_features.columns
df_edges_with_features['setyear'] = 2017

traffic_as_input = df_edges_with_features.drop(['u','v','key','osmid','geometry'],axis=1).sort_index(axis=1)
df_edges['aadb_predictions'] = regr.predict(traffic_as_input)

G_with_traffic_weights = ox.graph_from_gdfs(df_nodes,df_edges)
ox.plot.get_edge_colors_by_attr(G_with_traffic_weights,'aadb_predictions').shape()

ec = ox.plot.get_edge_colors_by_attr(G_with_traffic_weights, 'aadb_predictions', cmap='plasma',num_bins=20)
fig,ax = ox.plot_graph(G_with_traffic_weights, node_zorder=2,node_size=0.03,edge_linewidth=df_edges['aadb_predictions']*.002,node_alpha = 0.1,node_color='k', bgcolor='w',use_geom=True, axis_off=False,show=False, close=False)
fig,ax = ox.plot_graph(G_with_traffic_weights, node_zorder=2,node_size=0.03,edge_linewidth=1,edge_color=ec,node_alpha = 0.5,node_color='k', bgcolor='k',use_geom=True, axis_off=False,show=False, close=False)

tag_crashes(df_crashes,G_with_traffic_weights,df_nodes)

df_crashes_train = df_crashes[df_crashes['CRASH_YEAR'] != 2017]

number_of_crashes_at_a_node(df_crashes_train,G_with_traffic_weights,df_nodes)
df_nodes.head()
G_with_traffic_weights = ox.utils_graph.graph_from_gdfs(df_nodes,df_traffic_grouped)
fig,ax = ox.plot_graph(G_with_traffic_weights, node_zorder=2,node_size=df_nodes['number_of_accidents'],edge_linewidth=0,edge_color=ec,node_alpha = 1,node_color='w', bgcolor='k',use_geom=True, axis_off=False,show=False, close=False)
df_nodes.head()
G_with_traffic_weights = ox.graph_from_gdfs(df_nodes,df_edges)

df_traffic_grouped[df_traffic_grouped['v'] ==109729474 ]
G_with_traffic_weights.degree(109729474)
G_with_traffic_weights.degree(109729474,weight='aadb')
df_nodes['aadb'] = df_nodes.apply(lambda x: G_with_traffic_weights.degree(x['osmid'],weight='aadb_predictions'), axis=1)
df_nodes[df_nodes['osmid'] == 109729474]

## 1999 to 2016 is 17 years, 365 days
df_nodes['accidents/aadb'] = df_nodes['number_of_accidents'].div(df_nodes['aadb']) /365/17

fig,ax = ox.plot_graph(G_with_traffic_weights, node_zorder=2,node_size=df_nodes['number_of_accidents'],edge_linewidth=0,edge_color=ec,node_alpha = 1,node_color='w', bgcolor='k',use_geom=True, axis_off=False,show=False, close=False)
fig,ax = ox.plot_graph(G_with_traffic_weights, node_zorder=2,node_size=df_nodes['accidents/aadb']*10000000,edge_linewidth=0,edge_color=ec,node_alpha = 1,node_color='w', bgcolor='k',use_geom=True, axis_off=False,show=False, close=False)


df_nodes['aadb'].hist()
df_nodes['number_of_accidents'].hist()
df_nodes['accidents/aadb'].std()

df_nodes['accidents/aadb'].std()

alpha,beta = beta_values(df_nodes['accidents/aadb'].mean(),df_nodes['accidents/aadb'].std())
df_nodes['adjusted accidents/aadb'] = (df_nodes['number_of_accidents']+alpha).div(df_nodes['aadb']+alpha+beta)

def probability_func(r,df_nodes):
    u = r['u']
    v = r['v']
    return df_nodes.loc[u]['adjusted accidents/aadb'] + df_nodes.loc[v]['adjusted accidents/aadb']

def give_probabilities_to_edges(df_edges,df_nodes):
    df_edges['probability'] = df_edges.apply(lambda x: probability_func(x,df_nodes),axis=1)



give_probabilities_to_edges(df_edges,df_nodes)

df_edges.head()

fig,ax = ox.plot_graph(G_with_traffic_weights, node_zorder=2,node_size=0.00,node_alpha = 0.1,node_color='k', bgcolor='k', edge_linewidth=df_edges['probability']*300000,use_geom=True, axis_off=False,show=False, close=False)


df_edges.head()

df_edges.iloc[0][['u','v']]
ox.graph_to_gdfs(G_with_traffic_weights,edges=False)
u
v

df_edges['accident_prob'] = df_edges.apply


df_nodes['adjusted accidents/aadb'].describe()
len(df_nodes[df_nodes['adjusted accidents/aadb'] < 0.000301]) - len(df_nodes)


df_nodes[(df_nodes['number_of_accidents'] > 0)]['adjusted accidents/aadb'].min()
df_nodes[(df_nodes['adjusted accidents/aadb'] < 0.000191) & (df_nodes['number_of_accidents'] > 0)]

df_nodes.loc[110330155]
df_nodes.loc[110329806]
df_nodes[(df_nodes['adjusted accidents/aadb'] > 0.000181) & (df_nodes['number_of_accidents'] > 0)]

len(df_nodes[df_nodes['number_of_accidents'] == 0 ]) - len(df_nodes)

ax = df_nodes['adjusted accidents/aadb'].hist()
ax.set_xscale('log')
ax.set_yscale('log')

traffic_x
reg.coef_



gdf_traffic.plot()
k
df_traffic.columns
df_traffic.groupby(['closest_edge_u','closest_edge_v','setdate']).get_group((109729474,109729486,'2010/09/02 00:00:00+00'))
gdf_traffic_grouped = gpd.GeoDataFrame(df_traffic_grouped[['closest_edge_poly','aadb','road','setyear']])
gdf_traffic_grouped['geometry'] = gdf_traffic_grouped['closest_edge_poly']
gdf_traffic_grouped
gdf_traffic_grouped[gdf_traffic_grouped['aadb'] > 3000]
fig,ax = ox.plot_graph(G_traffic, node_zorder=2,node_size=0.03,edge_linewidth=df_traffic_grouped['aadb']*.002,node_alpha = 0.1,node_color='k', bgcolor='w',use_geom=True, axis_off=False,show=False, close=False)

gdf_traffic_grouped[gdf_traffic_grouped['aadb'] == 234].plot(ax=ax)

gdf_traffic_grouped[gdf_traffic_grouped['aadb'] == 354]

scheme = mapclassify.Quantiles(gdf_traffic_grouped['aadb'],k=5)
geoplot.choropleth(gdf_traffic_grouped, hue=gdf_traffic_grouped['aadb'],scheme=scheme,cmap='Greens')

df_traffic.describe()
df_traffic.count()
ox.get_nearest_edge(G,(r['Y'],r['X']),return_geom = True,return_dist = True)
df_traffic.apply(lambda x : traffic_func(x,G))


df_edges_with_features.columns
df_edges_with_features.head()

df_traffic.head()

edges= ox.graph_to_gdfs(G_undirected,nodes=False)
edges.count()
nx.edges(G_undirected,7244251137)
nx.edges(G,7244251137)
help(G_undirected.has_edge)
G_undirected.edges()



fig,ax = ox.plot_graph(G_undirected, node_zorder=2,node_size=0.03,node_alpha = 0.1,node_color='k', bgcolor='w', edge_linewidth=1,use_geom=True, axis_off=False,show=False, close=False)
#ax=df_crashes.plot(kind='scatter',x='DEC_LONG',y='DEC_LAT',s=1,fig=fig,label='Bike Accident',ax=ax)
ax = df_traffic.plot(title='Plotting the 3 Main Datasets',kind='scatter',x='X',y='Y',s=1,c='r',label='Traffic Study',fig=fig,ax=ax)
