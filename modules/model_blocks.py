
from tensorflow.keras.layers import Dropout, Dense, Concatenate, BatchNormalization, Add, Multiply, LeakyReLU
from Layers import OnesLike
from DeepJetCore.DJCLayers import  SelectFeatures, ScalarMultiply

from Initializers import EyeInitializer



from datastructures import TrainData_NanoML


def extent_coords_if_needed(coords, x, n_cluster_space_coordinates,name='coord_extend'):
    if n_cluster_space_coordinates > 3:
        x = Concatenate()([coords,x])
        extendcoords = Dense(n_cluster_space_coordinates-3,
                             use_bias=False,
                             name=name+'_dense',
                             kernel_initializer=EyeInitializer(stddev=0.001)
                             )(x)
        coords = Concatenate()([coords, extendcoords])
    return coords

#new format!
def create_outputs(x, energy=None, n_ccoords=3, 
                   n_classes=4,
                   fix_distance_scale=False,
                   scale_energy=False,
                   energy_factor=True,
                   energy_proxy=None,
                   name_prefix="output_module"):
    '''
    returns pred_beta, pred_ccoords, pred_energy, pred_energy_low_quantile,pred_energy_high_quantile,pred_pos, pred_time, pred_id
    '''
    assert scale_energy != energy_factor
    
    pred_beta = Dense(1, activation='sigmoid',name = name_prefix+'_beta')(x)
    pred_ccoords = Dense(n_ccoords,
                         #this initialisation is much better than standard glorot
                         kernel_initializer=EyeInitializer(stddev=0.001),
                         use_bias=False,
                         name = name_prefix+'_clustercoords'
                         )(x) #bias has no effect
    
    if energy_proxy is None:
        energy_proxy = x
    else:
        energy_proxy = Concatenate()([energy_proxy,x])
    energy_act=None
    if energy_factor:
        energy_act='relu'
    energy_res_act = LeakyReLU(alpha=0.3)
    pred_energy = Dense(1,name = name_prefix+'_energy',
                        bias_initializer='ones',
                        activation=energy_act
                        )(energy_proxy)
    pred_energy_low_quantile = Dense(1,name = name_prefix+'_energy_low_quantile',
                        bias_initializer='zeros',
                        activation=energy_res_act
                        )(energy_proxy)
    pred_energy_high_quantile = Dense(1,name = name_prefix+'_energy_high_quantile',
                        bias_initializer='zeros',
                        activation=energy_res_act
                        )(energy_proxy)
    if scale_energy:
        pred_energy = ScalarMultiply(10.)(pred_energy)
    if energy is not None:
        pred_energy = Multiply()([pred_energy,energy])
        pred_energy_low_quantile = Multiply()([pred_energy_low_quantile,energy])
        pred_energy_high_quantile = Multiply()([pred_energy_high_quantile,energy])
        
    pred_pos =  Dense(2,use_bias=False,name = name_prefix+'_pos')(x)
    pred_time = ScalarMultiply(10.)(Dense(1)(x))
    
    pred_id = Dense(n_classes, activation="softmax",name = name_prefix+'_class')(x)
    
    pred_dist = OnesLike()(pred_time)
    if not fix_distance_scale:
        pred_dist = ScalarMultiply(2.)(Dense(1, activation='sigmoid',name = name_prefix+'_dist')(x))
        #this needs to be bound otherwise fully anti-correlated with coordates scale
    return pred_beta, pred_ccoords, pred_dist, pred_energy, pred_energy_low_quantile, pred_energy_high_quantile, pred_pos, pred_time, pred_id




def re_integrate_to_full_hits(
        pre_selection,
        pred_ccoords,
        pred_beta,
        pred_energy_corr,
        pred_energy_low_quantile,
        pred_energy_high_quantile,
        pred_pos,
        pred_time,
        pred_id,
        pred_dist,
        dict_output=False,
        is_preselected=False,
        ):
    '''
    To be called after OC loss is applied to pre-selected outputs to bring it all back to the full dimensionality
    all hits that have been selected before and cannot be backgathered will be assigned coordinates far away,
    and a zero beta value.
    
    This is the counterpart of the pre_selection_model_full.
    
    returns full suite
    ('pred_beta', pred_beta), 
    ('pred_ccoords', pred_ccoords),
    ('pred_energy_corr_factor', pred_energy_corr),
    ('pred_energy_low_quantile', pred_energy_low_quantile),
    ('pred_energy_high_quantile', pred_energy_high_quantile),
    ('pred_pos', pred_pos),
    ('pred_time', pred_time),
    ('pred_id', pred_id),
    ('pred_dist', pred_dist),
    ('row_splits', row_splits)
    '''
    from GravNetLayersRagged import MultiBackScatterOrGather
    from globals import cluster_space as  cs
    
    if not is_preselected:
        scatterids = pre_selection['scatterids']
        pred_ccoords = MultiBackScatterOrGather(default=cs.noise_coord)([pred_ccoords, scatterids])#set it far away for noise
        pred_beta = MultiBackScatterOrGather(default=0.)([pred_beta, scatterids])
        pred_energy_corr = MultiBackScatterOrGather(default=1.)([pred_energy_corr, scatterids])
        pred_energy_low_quantile = MultiBackScatterOrGather(default=1.)([pred_energy_low_quantile, scatterids])
        pred_energy_high_quantile = MultiBackScatterOrGather(default=1.)([pred_energy_high_quantile, scatterids])
        pred_pos = MultiBackScatterOrGather(default=0.)([pred_pos, scatterids])
        pred_time = MultiBackScatterOrGather(default=10.)([pred_time, scatterids])
        pred_id = MultiBackScatterOrGather(default=0.)([pred_id, scatterids])
        pred_dist = MultiBackScatterOrGather(default=1.)([pred_dist, scatterids])
    
    row_splits = None
    if is_preselected:
        row_splits = pre_selection['row_splits']
    else:
        row_splits = pre_selection['orig_row_splits']
    
    if dict_output:
        return {
            'pred_beta': pred_beta, 
            'pred_ccoords': pred_ccoords,
            'pred_energy_corr_factor': pred_energy_corr,
            'pred_energy_low_quantile': pred_energy_low_quantile,
            'pred_energy_high_quantile': pred_energy_high_quantile,
            'pred_pos': pred_pos,
            'pred_time': pred_time,
            'pred_id': pred_id,
            'pred_dist': pred_dist,
            'row_splits': row_splits }
        
    return [
        ('pred_beta', pred_beta), 
        ('pred_ccoords', pred_ccoords),
        ('pred_energy_corr_factor', pred_energy_corr),
        ('pred_energy_low_quantile', pred_energy_low_quantile),
        ('pred_energy_high_quantile', pred_energy_high_quantile),
        ('pred_pos', pred_pos),
        ('pred_time', pred_time),
        ('pred_id', pred_id),
        ('pred_dist', pred_dist),
        ('row_splits', pre_selection['orig_row_splits'])]
    
    




from GravNetLayersRagged import AccumulateNeighbours, SelectFromIndices, SelectFromIndicesWithPad
from GravNetLayersRagged import SortAndSelectNeighbours, NoiseFilter
from GravNetLayersRagged import CastRowSplits, ProcessFeatures
from GravNetLayersRagged import GooeyBatchNorm, MaskTracksAsNoise
from LossLayers import LLClusterCoordinates, AmbiguousTruthToNoiseSpectator, LLNotNoiseClassifier, LLFillSpace, LLEdgeClassifier
from MetricsLayers import MLReductionMetrics, SimpleReductionMetrics
from Layers import CreateTruthSpectatorWeights

from tensorflow.keras.layers import Flatten, Reshape

from GravNetLayersRagged import NeighbourGroups,GroupScoreFromEdgeScores,ElementScaling, EdgeSelector, KNN, DistanceWeightedMessagePassing, RecalcDistances, MultiAttentionGravNetAdd
from DebugLayers import PlotCoordinates, PlotEdgeDiscriminator, PlotNoiseDiscriminator
    
#make this much simpler
def pre_selection_model(
        orig_inputs,
        debug_outdir='',
        trainable=False,
        name='pre_selection',
        debugplots_after=-1,
        reduction_threshold=0.51,#doesn't make a huge difference
        noise_threshold=0.1, #0.4 % false-positive, 96% noise removal
        K=12,
        record_metrics=True,
        filter_noise=True,
        ):
    
    if not 't_spectator_weight' in orig_inputs.keys(): #compat layer
        orig_t_spectator_weight = CreateTruthSpectatorWeights(threshold=5.,minimum=1e-1,active=True
                                                         )([orig_inputs['t_spectator'], 
                                                            orig_inputs['t_idx']])
        orig_inputs['t_spectator_weight'] = orig_t_spectator_weight
        
    if not 'is_track' in orig_inputs.keys():
        orig_inputs['is_track'] = SelectFeatures(2,3)(orig_inputs['features'])
        
    if not 'rechit_energy' in orig_inputs.keys():
        orig_inputs['rechit_energy'] = SelectFeatures(0, 1)(orig_inputs['features'])    
    
    processed_features =  orig_inputs['features']   
    #coords have not been built so features not processed
    if not 'coords' in orig_inputs.keys():
        processed_features = ProcessFeatures()(orig_inputs['features'])
        orig_inputs['coords'] = SelectFeatures(5, 8)(processed_features)
    
    #get some things to work with    
    orig_inputs['row_splits'] = CastRowSplits()(orig_inputs['row_splits'])
    rs = orig_inputs['row_splits']
    energy = orig_inputs['rechit_energy']
    coords = orig_inputs['coords']
    is_track = orig_inputs['is_track']
    x = processed_features
    
    #truth
    t_spec_w = orig_inputs['t_spectator_weight']
    t_idx = orig_inputs['t_idx']
    
    coords = ElementScaling(name=name+'es1',trainable=trainable)(coords)
    coords = LLClusterCoordinates(active = trainable,
        name = name+'_LLClusterCoordinates',record_metrics = record_metrics,
        scale=1.
        )([coords,t_idx,t_spec_w,energy, rs])
    
    
    
    nidx,dist = KNN(K=K,record_metrics=record_metrics,name=name+'_knn',
                    min_bins=20)([coords,rs])#hard code it here, this is optimised given our datasets
    
    ### this is the "meat" of the model
    
    x = DistanceWeightedMessagePassing([32,32],name=name+'dmp1',trainable=trainable)([x,nidx,dist])# hops are rather light 
    x = Dense(32,activation='relu',name=name+'dense1a',trainable=trainable)(x)
    x = Dense(32,activation='relu',name=name+'dense1b',trainable=trainable)(x)                
    
    #create reduction, very simple, this gets expanded with K! be careful
    x_e = Dense(6,activation='relu',name=name+'dense_x_e',trainable=trainable)(x)
    x_e = SelectFromIndicesWithPad()([nidx, x_e])#this will be big
    x_e = Flatten()(x_e)
    x_e = Dense(4*K,activation='relu',name=name+'dense_flat_x_e',trainable=trainable)(x_e)
    x_e = Reshape((K,4))(x_e)
    x_e = Dense(1,activation='sigmoid',name=name+'_ed3',trainable=trainable)(x_e)#edge classifier    
    
    
    cluster_tidx = MaskTracksAsNoise(active=trainable)([t_idx,is_track])
    x_e = LLEdgeClassifier( name = name+'_LLEdgeClassifier',active=trainable,record_metrics=record_metrics,
            scale=5.#high scale
            )([x_e,nidx,cluster_tidx, t_spec_w, energy])    
    
    
    if debugplots_after > 0:
        x_e = PlotEdgeDiscriminator(plot_every=debugplots_after,
                                        outdir=debug_outdir,name=name+'_edges')([x_e,nidx,cluster_tidx])
    
    sel_nidx = EdgeSelector(
            threshold=reduction_threshold
            )([x_e,nidx])
            
    sel_t_spec_w, sel_t_idx = AmbiguousTruthToNoiseSpectator(
        record_metrics=record_metrics)([sel_nidx, t_spec_w, t_idx])
                 
    hierarchy = GroupScoreFromEdgeScores()([x_e,sel_nidx])
    
    g_sel_nidx, g_sel, group_backgather, g_sel_rs = NeighbourGroups(threshold = 1e-3,return_backscatter=False,
        record_metrics = False)([hierarchy, sel_nidx, rs])
    
    
    g_sel = MLReductionMetrics(
        name=name+'_reduction_0',
        record_metrics = record_metrics
        )([g_sel,t_idx,orig_inputs['t_energy'],rs,g_sel_rs])
    
    #safety, these row splits are obsolete now  
    rs = None
    
    # g_sel_sel_nidx: selected selected indices (first dimension output vertex multi)
    # g_sel_nidx: 'old' dimension, but with -1s where neighbours are clusters elsewhere
    g_sel_sel_nidx = SelectFromIndices()([g_sel,g_sel_nidx])
    
    #create selected output truth
    out={}
    for k in orig_inputs.keys():
        if 't_' == k[0:2]:
            out[k] = SelectFromIndices()([g_sel,orig_inputs[k]])
    
    #consider ambiguities
    out['t_idx'] = SelectFromIndices()([g_sel,sel_t_idx])
    out['t_spectator_weight'] = SelectFromIndices()([g_sel,sel_t_spec_w])
    
    ## create reduced features
    
    x_to_flat = Concatenate(name=name+'concat_x_to_flat')([processed_features,x])
    x_to_flat = Dense(4, activation='relu',name=name+'flatten_dense')(x_to_flat)
    #this has output dimension now
    x_flat_o = SelectFromIndicesWithPad()([g_sel_sel_nidx, x_to_flat])
    x_flat_o = Flatten()(x_flat_o)
    
    x_o = AccumulateNeighbours('minmeanmax')([x, g_sel_nidx, energy])
    x_o = SelectFromIndices()([g_sel,x_o])
    x_o = Concatenate(name=name+'concat_x_o')([x_o,x_flat_o])
    x_o = GooeyBatchNorm(trainable=trainable)(x_o)
    
    #explicitly sum energy    
    energy_o = AccumulateNeighbours('sum')([energy, g_sel_nidx])
    energy_o = SelectFromIndices()([g_sel,energy_o])
    
    #build preselection coordinates
    coords_o = AccumulateNeighbours('mean')([coords, g_sel_nidx, energy])
    coords_o = SelectFromIndices()([g_sel,coords_o])
    
    ## selection done work on selected ones
    
    coord_add_o = Dense(16,activation='relu',name=name+'dense_coord_add1')(x_o)
    coord_add_o = Dense(3,name=name+'dense_coord_add3')(coord_add_o)
    coords_o = Add()([coords_o,coord_add_o])
    
    #was not clustered
    is_track_o = SelectFromIndices()([g_sel,is_track])
    
    #create a gradient for this
    coords_o = LLClusterCoordinates(
        record_metrics=record_metrics,
        name = name+'_LLClusterCoordinates_coords_o',
        active = trainable,
        scale=1.
        )([coords_o,out['t_idx'],out['t_spectator_weight'],energy_o,g_sel_rs])
    
    
    
    #add to dict:
    out['coords'] = coords_o
    out['rechit_energy'] = energy_o
    out['features'] = x_o
    out['is_track'] = is_track_o
    
    if debugplots_after>0:
        out['coords'] = PlotCoordinates(plot_every=debugplots_after,
                                        outdir=debug_outdir,name=name+'_after_red')(
                                            [out['coords'],
                                             out['rechit_energy'],
                                             out['t_idx'],g_sel_rs])
    
    ####### noise filter part #########
    
    scatterids=None
    
    if filter_noise:
    
        isnotnoise = Dense(1, activation='sigmoid',trainable=trainable,name=name+'_noisescore_d1',
                           )(Concatenate(name=name+'concat_outf_outc')([out['features'],out['coords']]))
                           
        track_adjusted_t_idx = MaskTracksAsNoise(maskidx=1,active=trainable)([out['t_idx'],out['is_track']])
        isnotnoise = LLNotNoiseClassifier(active=trainable,record_metrics=record_metrics,
            scale=1.)([isnotnoise, track_adjusted_t_idx])
        
        if debugplots_after > 0:
            isnotnoise = PlotNoiseDiscriminator(plot_every=debugplots_after,
                                        outdir=debug_outdir,name=name+'_noise_score')([isnotnoise,track_adjusted_t_idx])
                                        
        no_noise_sel, no_noise_rs, noise_backscatter = NoiseFilter(threshold = noise_threshold,record_metrics=record_metrics
            )([isnotnoise,g_sel_rs])
        
        
        #select not-noise
        for k in out.keys():
            out[k] = SelectFromIndices()([no_noise_sel,out[k]]) #also  good check, will fail if dimensions don't match
        
        #safety, these row splits are obsolete now 
        g_sel_rs = None
    
        out['row_splits'] = no_noise_rs
        scatterids = [group_backgather, noise_backscatter]
        
    else:
        out['row_splits'] = g_sel_rs
        scatterids = [group_backgather]
        
    if 'scatterids' in orig_inputs.keys():
        out['scatterids'] = orig_inputs['scatterids'] + scatterids
    else:
        out['scatterids'] = scatterids
        
    if not 'orig_row_splits' in orig_inputs.keys():
        out['orig_row_splits'] = orig_inputs['row_splits']
    else:
        out['orig_row_splits'] = orig_inputs['orig_row_splits']#pass through
    
    # full reduction metric
    out['row_splits'] = SimpleReductionMetrics(
        name=name+'full_reduction',
        record_metrics=record_metrics
        )([out['row_splits'],orig_inputs['row_splits']])
    
    return out
    
    
    