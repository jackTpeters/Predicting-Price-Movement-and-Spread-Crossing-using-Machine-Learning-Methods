import functools as fn
import datetime
import math
import pdb

import pandas as pd
import numpy as np
import scipy.stats as scs

# from sklearnex import patch_sklearn ## Must run patch before importing other sklearn functions!!!
# patch_sklearn()
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.svm import SVC
from sklearn.model_selection import StratifiedShuffleSplit
from sklearn.metrics import classification_report, confusion_matrix

from matplotlib import pyplot as plt
#import plotly.graph_objects as go

pd.options.mode.chained_assignment = None  # shaving with a machete...

def ts_to_secs(ptimestamp):
    str_zpad = str(ptimestamp).zfill(15)
    return int(str_zpad[:2])*3600 + int(str_zpad[2:4])*60 + int(str_zpad[4:6]) + 1e-9 *float(str_zpad[6:])
def ts_to_pdts(ptimestamp, dte):
    """
    dte should be day of TAQ timestamp as datetime.datetime instance
    """
    str_zpad = str(ptimestamp).zfill(15)
    
    return pd.Timestamp(dte.year, dte.month, dte.day, 
                 int(str_zpad[:2]), int(str_zpad[2:4]), 
                int(str_zpad[4:6]), 0, int(str_zpad[6:]))

def taq2mox(q):
    """
    Adds MOX identifier to the raw quotes data. 

    Parameters:
    -------------
   
    q : pd.DataFrame
        raw TAQ quotes dataframe from csv
        
    Returns:
    ---------
    q : pd.DataFrame
        quotes with MOX id added
    """
    q.sort_values(['Participant_Timestamp','Sequence_Number'], axis =0, inplace=True)
    q['MOX'] = q.groupby('Participant_Timestamp').ngroup()
    
    return q

def clean_quotes(q):
    """
    Filters raw quotes data by removing first and last 15 minutes. Removes alternative display facilities quotes as well as
    trade through exempt quotes. Adds MOX identifier to the output and uses this to remove mechanical quote updates. The intention
    is to have onyl actual, valid historical quotes remaining in the output.

    Parameters:
    -------------
   
    q : pd.DataFrame
        raw TAQ quotes dataframe from csv
    
        
    Returns:
    ---------
    q_valid_LAQ : pd.DataFrame
        cleaned quotes with numerical Participant_Timestamp (pt_secs) and MOX identifier added
    """
    q.sort_values(by=['Participant_Timestamp','Sequence_Number'],axis=0, inplace=True )
    q_v = q[np.logical_and(q['Participant_Timestamp'] >= 94500000000000, q['Participant_Timestamp'] <= 154500000000000) ] 
    q_v['pt_secs'] = q_v['Participant_Timestamp'].apply(ts_to_secs)
    q_v = q_v.iloc[~(q_v['Exchange'] =='D').to_numpy()]
    q_v = taq2mox(q_v)

    qdiff = q_v['MOX'].diff().to_numpy()
    diff_mox = (qdiff ==1.0)
    mask_natural = diff_mox[:-1] * diff_mox[1:]  # unique MOX only - solo quotes
    mask_lastmqu = (qdiff[:-1] - qdiff[1:]) == -1.0

    mask_valid_LAQ = np.concatenate(([False],np.logical_or(mask_natural, mask_lastmqu)))
    q_valid_LAQ = q_v.iloc[mask_valid_LAQ ,:]
    
    return q_valid_LAQ
def valid_trades(t,q):
    """
    Takes raw trades and quoters and returns a trades dataframe with only valid trades (not sec611 or ADF trade) and
    attaches the last active best bid and best offer at time of trade. 

    Parameters:
    -------------
    t : pd.DataFrame
        raw TAQ trades dataframe from csv
    q : pd.DataFrame
        raw TAQ quotes dataframe from csv
    
    Returns:
    ---------
    t_valid : pd.DataFrame
        cleaned trades with numerical Participant_Timestamp (pt_secs), MOX identifier and LAQ bid/offer appended 

    """
    df_LAQ = clean_quotes(q)
    df_LAQ = df_LAQ[['pt_secs', 'Sequence_Number', 'Best_Bid_Price', 'Best_Offer_Price']]
    df_LAQ.reset_index(inplace=True)
    t.sort_values(by=['Participant_Timestamp','Sequence_Number'],axis=0, inplace=True )
    t_v = t[np.logical_and(t['Participant_Timestamp'] >= 94500000000000, t['Participant_Timestamp'] <= 154500000000000) ] 
    t_v['pt_secs'] = t_v['Participant_Timestamp'].apply(ts_to_secs)
    t_v = t_v.iloc[~(t_v['Exchange'] =='D').to_numpy()] ## remove ADF - trades need not obey nbbo quotes
    t_v = t_v[ ~ (t_v['Trade_Through_Exempt_Indicator'] == 1)]

    t_v['tMOX'] = t_v.groupby('Participant_Timestamp').ngroup()
    tdiff = t_v['tMOX'].diff().to_numpy()
    diff_mox = (tdiff ==1.0)
    mask_natural = diff_mox[:-1] * diff_mox[1:]  # unique MOX only - solo quotes
    mask_lasttrade = (tdiff[:-1] - tdiff[1:]) == -1.0

    mask_valid_trade = np.concatenate(([False],np.logical_or(mask_natural, mask_lasttrade)))
    t_valid = t_v.iloc[mask_valid_trade ,:]
    df_temp = t_valid[['pt_secs', 'Sequence_Number']]
    df_temp.sort_values('Sequence_Number', inplace=True)
    df_temp['pt_secs'] =  t_valid['pt_secs'].to_numpy() + 1e-7 # smallest diff between pt_sec values, machine eps instead??
    df_temp['is_trade'] = True
    df_temp[['Best_Bid_Price', 'Best_Offer_Price']] = np.nan 
    df_LAQ['is_trade'] = False

    df_temp = df_temp.append(df_LAQ)
    df_temp.sort_values('pt_secs', inplace=True)
    df_temp.ffill(inplace=True)
    df_valid_trades = df_temp[df_temp['is_trade']==True]
    t_v.set_index('Sequence_Number', inplace=True)
    t_v.sort_index(inplace=True)
    df_valid_trades.set_index('Sequence_Number', inplace=True)
    df_valid_trades.sort_index(inplace=True)
    t_valid[['LAQ_bid','LAQ_offer']] =  df_valid_trades[['Best_Bid_Price', 'Best_Offer_Price']].to_numpy()
    return t_valid





def raw_tq2mox_old(t, q):
    """
    Modifies raw quote and trade data. Tsimsfirst/last 15 minutes 
    of normal trading hours. Adds MOX identifier and LAQ (Last active quote).

    Parameters:
    -------------
    t : pd.DataFrame
        raw TAQ trades dataframe from csv
    q : pd.DataFrame
        raw TAQ quotes dataframe from csv
        
    Returns:
    ---------

    t_v : pd.DataFrame
        cleaned trades with MOX id , LAQ - Last active quote
    q_v : pd.DataFrame
        cleaned quotes with MOX id
    """
    t.sort_values(by=['Participant_Timestamp','Sequence_Number'], axis=0, inplace=True)
    q.sort_values(by=['Participant_Timestamp','Sequence_Number'],axis=0, inplace=True )
    t_v = t[np.logical_and(t['Participant_Timestamp'] >= 94500000000000, t['Participant_Timestamp'] <= 154500000000000) ] # remove closing/opening auction dissemination ( remove first and last 15 min), formally->3:50pm NYSE/NASDAQ (closing cross)
    q_v = q[np.logical_and(q['Participant_Timestamp'] >= 94500000000000, q['Participant_Timestamp'] <= 154500000000000) ] 
    t_v['pt_secs'] = t_v['Participant_Timestamp'].apply(ts_to_secs)
    q_v['pt_secs'] = q_v['Participant_Timestamp'].apply(ts_to_secs)

    ### Assigning MOX to trades and quotes
    
    mox = 1 # MOX of zero saved for exchange updated quotes versus MQUs
    j = 0 
    N = len(t_v)
    t_v['MOX'] = np.full(N, np.nan, dtype=int)
    while j < N:
        cur_pts = t_v['Participant_Timestamp'].iloc[j]
        while j < N and  cur_pts == t_v['Participant_Timestamp'].iloc[j]:
            t_v['MOX'].iloc[j] = mox
            j +=1
        mox += 1
    # MOX of zero saved for exchange updated quotes versus MQUs
    j = 0 
    N = len(q_v)
    q_v['MOX'] = np.full(N, np.nan,dtype=int)
    while j < N:
        cur_pts = q_v['pt_secs'].iloc[j]
        df_trade_moxes = t_v[t_v['pt_secs'] == cur_pts]
        if len(df_trade_moxes) == 0 or len(df_trade_moxes) == 1: # MQU with only 1 trade/quote update
            q_v['MOX'].iloc[j] = 0
        else:
            #pdb.set_trace()
            q_v['MOX'].iloc[j] = df_trade_moxes['MOX'].iloc[0]
        j +=1
    t_v['LAQ_bid'] = np.zeros(len(t_v))
    t_v['LAQ_offer'] = np.zeros(len(t_v))
    t_v['LAQ_pt'] = np.zeros(len(t_v))
    t_v['LAQ_bid_size'] = np.zeros(len(t_v))
    t_v['LAQ_offer_size'] = np.zeros(len(t_v))
    ## mask for last MQU or natural quotes only

    mask_natural = (q_v['MOX'] == 0).to_numpy()
    mask_lastmqu = np.concatenate(([True], mask_natural[1:]))
    mask_valid_LAQ = np.logical_or(mask_natural, mask_lastmqu)
    q_valid_LAQ = q_v.iloc[mask_valid_LAQ,:]
    for i in t_v.index.to_numpy():
        cur_pt = t_v['pt_secs'].loc[i]

        try:
            vquotes = q_valid_LAQ[np.logical_and(q_valid_LAQ['pt_secs'] >= cur_pt - 0.1, q_valid_LAQ['pt_secs'] <= cur_pt )].iloc[-1]
            t_v['LAQ_bid'].loc[i] = vquotes['Best_Bid_Price'] 
            t_v['LAQ_offer'].loc[i] = vquotes['Best_Offer_Price']  
            t_v['LAQ_bid_size'].loc[i] = vquotes['Best_Bid_Size'] 
            t_v['LAQ_offer_size'].loc[i] = vquotes['Best_Offer_Size']  
            t_v['LAQ_pt'].loc[i] = vquotes['pt_secs'] 
        except:
            t_v['LAQ_bid'].loc[i] = np.nan
            t_v['LAQ_offer'].loc[i] = np.nan 
            t_v['LAQ_pt'].loc[i] = np.nan
            t_v['LAQ_bid_size'].loc[i] =np.nan
            t_v['LAQ_offer_size'].loc[i] = np.nan
    return t_v, q_v


def gen_basic_features_TAQ(t_v, q_v, day=datetime.datetime(2020,1,6),
                str_filename="clean_features_"):
    """
    From clean trades and quotes dataframes built from TAQ data, generates simple features 
    
    num_events: int
        number of events ahead to build predict targets
    """
    pdts = fn.partial(ts_to_pdts, dte=day)
    q_v['pdts'] = q_v['Participant_Timestamp'].apply(pdts)
    pdts = fn.partial(ts_to_pdts, dte=day)
    q_v['pdts'] = q_v['Participant_Timestamp'].apply(pdts)

    q_v.set_index('pdts',inplace=True)
    q_v.sort_index(inplace=True)

    q_v['dPbid'] = q_v['Best_Bid_Price'].diff()
    q_v['dPask'] = q_v['Best_Offer_Price'].diff()
    q_v['dVbid'] = q_v['Best_Bid_Size'].diff()
    q_v['dVask'] = q_v['Best_Offer_Size'].diff()
    q_v[['ddPbid','ddPask','ddVbid','ddVask']] = q_v[['dPbid','dPask','dVbid','dVask']].rolling('1s').sum()
    df_trade_features = pd.DataFrame(index=np.arange(len(t_v) + len(q_v)),
                                 columns=['id','tprice','tvolume', 'Participant_Timestamp','is_trade'])
   
    df_trade_features.iloc[:len(t_v)] = np.hstack((t_v[['Sequence_Number', 'Trade_Price', 'Trade_Volume', 'Participant_Timestamp']].to_numpy(),
                                                np.ones((len(t_v),1))
                                                ))
    
    
    q_v_temp = np.hstack((q_v['Sequence_Number'].to_numpy().reshape(-1,1),
                                np.zeros((len(q_v),2)), 
                                q_v['Participant_Timestamp'].to_numpy().reshape(-1,1),
                                np.zeros((len(q_v),1))
                                 ))
 

    df_trade_features.iloc[len(t_v):] = q_v_temp
    pdts = fn.partial(ts_to_pdts, dte=day) # adjust date accordingly
    df_trade_features['pdts'] = df_trade_features['Participant_Timestamp'].astype(np.int64).apply(pdts)
    df_trade_features.set_index('pdts', inplace=True)
    df_trade_features.sort_index(inplace=True)
    df_trade_features[['avg_trade_price_10ms','avg_trade_volume_10ms']] = df_trade_features[['tprice','tvolume']].rolling('10ms').mean()
    df_trade_features[['avg_trade_price_100ms','avg_trade_volume_100ms']] = df_trade_features[['tprice','tvolume']].rolling('100ms').mean()
    df_trade_features[['avg_trade_price_1s','avg_trade_volume_1s']] = df_trade_features[['tprice','tvolume']].rolling('1s').mean()
    df_trade_features[['avg_trade_price_10s','avg_trade_volume_10s']] = df_trade_features[['tprice','tvolume']].rolling('10s').mean()
    q_v_update = df_trade_features[df_trade_features['is_trade'] != 1.0]
    q_v_update.set_index('id',inplace=True)
    q_v_update.sort_index(inplace=True)
    try:
        q_v.set_index('Sequence_Number',inplace=True)
    except:
        pass # index already set
    q_v.sort_index(inplace=True)
    q_v[['avg_trade_price_1s','avg_trade_volume_1s',
        'avg_trade_price_10s','avg_trade_volume_10s' ]] = np.zeros((len(q_v), 4))
    q_v.loc[q_v_update.index.to_numpy(),
        ['avg_trade_price_10ms','avg_trade_volume_10ms',
        'avg_trade_price_100ms','avg_trade_volume_100ms',
        'avg_trade_price_1s','avg_trade_volume_1s',
        'avg_trade_price_10s','avg_trade_volume_10s' ]]  = q_v_update[['avg_trade_price_100ms','avg_trade_volume_100ms', 'avg_trade_price_10ms','avg_trade_volume_10ms', 
                                                                        'avg_trade_price_1s','avg_trade_volume_1s', 'avg_trade_price_10s','avg_trade_volume_10s' ]].to_numpy()
    #['Sequence_Number'] = q_v.index.to_numpy()
    q_v.reset_index(inplace=True)
    q_valid_LAQ = clean_quotes(q_v)
    q_valid_LAQ['Best_Mid_Price'] = 0.5*(q_valid_LAQ['Best_Bid_Price'] + q_valid_LAQ['Best_Offer_Price'])    
    bid_price = q_valid_LAQ['Best_Bid_Price'].to_numpy()
    ask_price = q_valid_LAQ['Best_Offer_Price'].to_numpy()
    
    #price and volume features
    ask_volume = q_valid_LAQ['Best_Offer_Size'].to_numpy()
    bid_volume = q_valid_LAQ['Best_Bid_Size'].to_numpy()

    # spreads, first level only
    mid_price = q_valid_LAQ['Best_Mid_Price'].to_numpy()
   
    spread =ask_price - bid_price

    # derivatives, averaged over last t seconds
    t = 1.0 # Maybe make this a parameter or add more features like this
    ddPask_dt = np.nan_to_num(q_valid_LAQ['ddPask'].to_numpy())
    ddPbid_dt = np.nan_to_num(q_valid_LAQ['ddPbid'].to_numpy())
    ddVask_dt = np.nan_to_num(q_valid_LAQ['ddVask'].to_numpy())
    ddVbid_dt = np.nan_to_num(q_valid_LAQ['ddVbid'].to_numpy())


    # trade-based features
    # 'avg_trade_price_1s','avg_trade_volume_1s',
    # 'avg_trade_price_10s','avg_trade_volume_10s' 
    avg_trade_price_10ms   =  q_valid_LAQ['avg_trade_price_10ms'].to_numpy()
    avg_trade_price_100ms  =  q_valid_LAQ['avg_trade_price_100ms'].to_numpy()
    avg_trade_volume_10ms  =  q_valid_LAQ['avg_trade_volume_10ms'].to_numpy()
    avg_trade_volume_100ms=  q_valid_LAQ['avg_trade_volume_100ms'].to_numpy()

    avg_trade_price_1s   =  q_valid_LAQ['avg_trade_price_1s'].to_numpy()
    avg_trade_price_10s  =  q_valid_LAQ['avg_trade_price_10s'].to_numpy()
    avg_trade_volume_1s  =  q_valid_LAQ['avg_trade_volume_1s'].to_numpy()
    avg_trade_volume_10s =  q_valid_LAQ['avg_trade_volume_10s'].to_numpy()

    time = q_valid_LAQ['pt_secs'].to_numpy()

    dict_data = {
            'id'        : q_valid_LAQ['Sequence_Number'],
            'time'      : time,
            'ask_price' : ask_price,
            'bid_price' : bid_price,
            'ask_volume':ask_volume,
            'bid_volume': bid_volume,
            'mid_price' : (ask_price + bid_price) / 2.0,
            'spread'    : ask_price - bid_price,
            'dPask_dt'  : ddPask_dt,
            'dPbid_dt'  : ddPbid_dt,
            'dVask_dt'  : ddVask_dt,
            'dVbid_dt'  : ddVbid_dt,
            'avg_trade_price_10ms'   : avg_trade_price_10ms,
            'avg_trade_price_100ms'  :  avg_trade_price_100ms,
            'avg_trade_price_1s'   : avg_trade_price_1s,
            'avg_trade_price_10s'  :  avg_trade_price_10s,
            'avg_trade_volume_10ms'  :  avg_trade_volume_10ms,
            'avg_trade_volume_100ms' :  avg_trade_volume_100ms,
            'avg_trade_volume_1s'  :  avg_trade_volume_1s,
            'avg_trade_volume_10s' :  avg_trade_volume_10s,
            }
    
    df_clean = pd.DataFrame( data=dict_data)
    

    if not isinstance(str_filename,type(None)): # saves as feather file
        df_clean.reset_index(inplace=True)
        df_clean.to_feather(str_filename + day.strftime("%Y%m%d")+'e.f')
    df_clean.set_index('id', inplace=True)
    return df_clean



def gen_targets_events(q_v, num_events=30, 
                       day=datetime.datetime(2020,1,6),
                       str_filename="clean_targets_"):
    #q_v['Sequence_Number'] = q_v.index.to_numpy()
    q_valid_LAQ = clean_quotes(q_v)
    
    #num_events = int(30) # Passed as argument
    q_valid_LAQ['Best_Mid_Price'] = (q_valid_LAQ['Best_Bid_Price'] + q_valid_LAQ['Best_Offer_Price'])/2.0
    # find mid-price up moves
    mids = q_valid_LAQ['Best_Mid_Price'].to_numpy()
    mask_midup = (mids[num_events:] > mids[:-num_events])
    mask_middown = (mids[num_events:] < mids[:-num_events])
    mask_mideq = (mids[num_events:] == mids[:-num_events])
    #np.sum(mask_midup), np.sum(mask_middown), np.sum(mask_mideq), 
    bids = q_valid_LAQ['Best_Bid_Price'].to_numpy()
    asks = q_valid_LAQ['Best_Offer_Price'].to_numpy()
    mask_spreadup = (bids[num_events:] > asks[:-num_events])
    mask_spreaddown = (asks[num_events:] < bids[:-num_events])
    mask_spreadeq = np.logical_and(asks[num_events:] >= bids[:-num_events], bids[num_events:] <= asks[:-num_events])

    time = q_valid_LAQ['pt_secs'][:-num_events]
    dict_data = {
            'id'        : q_valid_LAQ['Sequence_Number'][:-num_events],
            'time'      : time,
            'midup'     : mask_midup,
            'middown'   : mask_middown,
            'mideq'     : mask_mideq,
            'spreadup'  : mask_spreadup,
            'spreaddown': mask_spreaddown,
            'spreadeq'  : mask_spreadeq,
         
            }
    df_clean = pd.DataFrame( data=dict_data)
    if not isinstance(str_filename,type(None)): # saves as feather file
        df_clean.reset_index(inplace=True)
        df_clean.to_feather(str_filename + str(num_events) +'e_' + day.strftime("%Y%m%d") + '.f')
    return df_clean


def gen_targets_temporal(    
                             q_v, 
                             prediction_interval=100, # milliseconds ahead to predict
                             day=datetime.datetime(2020,1,6),
                             str_filename="clean_targets_" 
                        ):
    #q_v['Sequence_Number'] = q_v.index.to_numpy()
    
    q_valid_LAQ = clean_quotes(q_v)
    last_time = q_valid_LAQ['pt_secs'].iloc[-1]
    df_temp = q_valid_LAQ[['pt_secs','Best_Bid_Price', 'Best_Offer_Price','Sequence_Number']].copy().reset_index()
    df_temp['lookahead'] = False
    df_lookahead = df_temp.copy()
    df_lookahead['pt_secs'] = df_lookahead['pt_secs'] + prediction_interval*1e-6 # milliseconds to seconds conversion
    df_lookahead['lookahead'] = True
    try:
        df_lookahead.set_index('pt_secs', inplace=True)
    except KeyError:
        pass # already set index
    df_lookahead[['Best_Bid_Price', 'Best_Offer_Price']] = np.nan
    try:
        df_temp.set_index('pt_secs', inplace=True)
    except KeyError:
        pass # already set index
    df_temp =  df_temp.append(df_lookahead)
    df_temp.sort_index(inplace=True)
    df_temp.ffill(inplace=True)
    df_temp.reset_index(inplace=True)
    df_temp.drop(df_temp.index.to_numpy()[~df_temp['lookahead']], inplace=True)
    df_temp.rename({'Best_Bid_Price': 'Best_Bid_Price' + str(prediction_interval)+ 'ms',
                    'Best_Offer_Price' : 'Best_Offer_Price' + str(prediction_interval)+ 'ms'},
                    axis =1, inplace=True )

    df_temp.set_index('Sequence_Number', inplace=True)
    pred_targets =['Best_Offer_Price', 'Best_Bid_Price']
    ncol = [_+str(prediction_interval)+'ms' for _ in pred_targets]
    q_valid_LAQ.set_index('Sequence_Number', inplace=True)
    q_valid_LAQ[ncol] = df_temp[ncol]
    q_valid_LAQ['Best_Mid_Price'] = 0.5*(q_valid_LAQ['Best_Bid_Price'] + q_valid_LAQ['Best_Offer_Price'])
    q_valid_LAQ['Best_Mid_Price'+str(prediction_interval)+'ms'] = 0.5*(q_valid_LAQ['Best_Bid_Price'+str(prediction_interval)+'ms'] + q_valid_LAQ['Best_Offer_Price'+str(prediction_interval)+'ms'] )
    fmids = q_valid_LAQ['Best_Mid_Price'+str(prediction_interval)+ 'ms'].to_numpy()
    mids = q_valid_LAQ['Best_Mid_Price'].to_numpy()
    mask_midup = fmids > mids
    mask_middown = fmids <  mids
    mask_mideq = fmids == mids

    fbids = q_valid_LAQ['Best_Bid_Price'+str(prediction_interval)+ 'ms'].to_numpy()
    fasks = q_valid_LAQ['Best_Offer_Price'+str(prediction_interval)+ 'ms'].to_numpy()
    bids = q_valid_LAQ['Best_Bid_Price'].to_numpy()
    asks = q_valid_LAQ['Best_Offer_Price'].to_numpy()

    mask_spreadup = fbids > asks
    mask_spreaddown = fasks < bids
    mask_spreadeq = np.logical_and(fasks >= bids,  fbids <= asks)
    time = q_valid_LAQ['pt_secs'].to_numpy()
    dict_data = {
            'id'        : q_valid_LAQ.index.to_numpy(),
            'time'      : time,
            'midup' + str(prediction_interval)+ 'ms'      : mask_midup,
            'middown' + str(prediction_interval)+ 'ms'    : mask_middown,
            'mideq'  + str(prediction_interval)+ 'ms'     : mask_mideq,
            'spreadup' + str(prediction_interval)+ 'ms'   : mask_spreadup,
            'spreaddown' + str(prediction_interval)+ 'ms' : mask_spreaddown,
            'spreadeq' + str(prediction_interval)+ 'ms'   : mask_spreadeq,   
            }

    ## drop values after original data's last time
    df_clean = pd.DataFrame( data=dict_data)
    df_clean.drop(df_clean.index.to_numpy()[df_clean['time'] > last_time - 1.0], inplace=True)


    if not isinstance(str_filename,type(None)): # saves as feather file
        df_clean.reset_index(inplace=True)
        df_clean.to_feather(str_filename + str(prediction_interval) +'ms_' + day.strftime("%Y%m%d") + '.f')
    return df_clean



