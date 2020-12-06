import time
import datetime as dt
import math
import numpy as np 
import pandas as pd
from scipy.signal import butter,filtfilt
from scipy import interpolate
from scipy.interpolate import interp1d

def diffed(sig):
    ''' This function takes the difference of a time series
     and reinterpolates to the original sample times with extrapolation.
     The calculation presumes first order smoothness of the time series and evenly
     sampled values (constant sample rate.)     
    Because diff() on dataframes introduces NaNs and artificially shifts values. *sigh*

     Input:
         sig - evenly sampled (>=10 Hz) chest expansion recording of respiration
              as a Pandas Dataframe or Series with timestamps as floats in index
     Output:
        dsig - new dataframe with the same index (sample points) as sig, with diffed values
              
    Related libraries: 
    from scipy import interpolate
    import numpy as np
    import pandas as pd
    ''' 

    if not isinstance(sig, pd.DataFrame):
        sig = sig.to_frame()
    cols = sig.columns
    xnew = sig.index
    dsig = pd.DataFrame(index = xnew)
    dt = np.nanmean(np.diff(sig.index))
    for c in cols:
        d = sig[c].diff()
        d=d.iloc[1:]
        y = d.values
        x=d.index-0.5*dt
        f = interpolate.interp1d(x, y,fill_value='extrapolate')
        ynew = f(xnew)   # use interpolation function returned by `interp1d`
        dsig[c] = ynew
    return dsig

def respnormed(sig,scaling=0):
    ''' a function to filter and normalise chest expansion recordings of respiration
    Respiration functions are bandpass filtered with cutoffs [0.05, 1] Hz
    zero phase butterworth.
    
    Input:
        sig - evenly sampled (>=10 Hz) chest expansion recording of respiration
              as a Pandas Dataframe or Series with timestamps as floats in index
        scaling - optional argument for setting the scaling constant.
              If blank, the function scales by median inspiration velocity 
              If scaling=1, the function presevers the input signal unites (but sets average to 0)
              If scaling=C, the signal values are multiplied by the float C
    Output:
        nsig - new dataframe with the same index (sample points) as sig, 
              with sig filtered and normalised according to inputs.
    
    Related libraries: 
    from scipy.signal import butter,filtfilt
    import numpy as np
    import pandas as pd
    ''' 

    if not isinstance(sig, pd.DataFrame):
        sig = sig.to_frame()
        
    if not scaling==0:
        autoscale=False
    else:
        autoscale=True
        
    times = sig.index
    cols = sig.columns
    d = sig.add(-sig.mean())
    
    nsig = pd.DataFrame(index = times)
    dt = np.nanmean(np.diff(sig.index))
    fs = round(1/dt)
    
    cutoff = np.array([0.05,1]) 
    nyq = 0.5 * fs 
    order = 2 
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='bandpass', analog=False)
        
    for c in cols:
        s = d[c].loc[d[c].notna()]
        y = filtfilt(b, a, s)
        if autoscale:
            x = pd.Series(y/(fs*np.median(abs(np.diff(y)))),index=s.index)
        else:
            x = pd.Series(scaling*y,index=s.index)
        nsig[str(c)] = x

    return nsig

def Inspiration_Extract(sig,filtered=False):
    ''' a function to extract the onsets of inspirations and expirations from chest expansion
    measurements. Parameters and criteria suitable recordings of respiration 
    on human adults without exertion or core movements or vocalisation. 
    Inspiration onsets are defined by a minimum chest expansion velocity rather local minima
    Expiration onsets are defined by local maxima (for passive expiration)
    This algorithm uses zero-crossing technique derived from Matsuda et al. and Upham 2018
    
    Input:
        sig - evenly sampled (>=10 Hz) chest expansion recording of respiration
              as a Pandas Dataframe or Series with timestamps as floats in index
        filtered - optional input (true false)
                If false (default), sig will passed to function respnormed
                If True, sig will evaluated directly, as its presumably been filtered 
    Output:
        Breaths - two column dataframe with Inpsiration onset ('In')
                  and Expiration onset ('Ex') timepoints in signal 
                  index values. 
    
    Related libraries: 
    from scipy.signal import butter,filtfilt
    import numpy as np
    import pandas as pd
    local functions: respnormed, diffed
    ''' 
    # evaluate sampling parameters
    dt = np.nanmean(np.diff(sig.index))
    sf = round(1/dt)
    # creat parallel dataframe to input sig
    df_sig = pd.DataFrame(sig.values,index=sig.index)
    df_sig = df_sig.rename(columns={0:'Raw'})
    # remove nans (they sneak in)
    df_sig = df_sig.loc[df_sig['Raw'].notna()]-df_sig.loc[df_sig['Raw'].notna()].mean()
    
    #prep derivatives of respiration signal
    newResp = pd.DataFrame(index = df_sig.index)
    if not filtered:
        newResp['Raw'] = df_sig['Raw']
        newResp['Filt'] = respnormed(newResp['Raw'],scaling=1)
    else:
        newResp['Filt'] = df_sig['Raw']
    newResp['Diff1'] = diffed(newResp['Filt'])
#     newResp['Diff2'] = diffed(newResp['Diff1'])
#     newResp['Diff3'] = diffed(newResp['Diff2'])

    # set thresholds according the signal distributions
    InspThresh = newResp['Diff1'].loc[newResp['Diff1']>0].mean()*sf*0.55
    VelThresh = InspThresh/sf; # to exclud very small bumps in chest expansion
    
    # catch inspirations from zero crossings
    cutoff = 0.2 
    nyq = 0.5 * sf 
    order = 2 
    normal_cutoff = cutoff / nyq
    b, a = butter(order, normal_cutoff, btype='low', analog=False)
    newResp['Flatten'] = filtfilt(b, a, newResp['Filt'])
    newResp['Crossings'] = (np.sign(newResp['Filt']- filtfilt(b, a, newResp['Filt']))).diff()
    insp = newResp['Filt'].loc[newResp['Crossings']==2]

    # Define inspiration intervals on stretch derivative 
    V = newResp['Diff1'].copy()
    #V.loc[V<0] = 0
    V.loc[V<VelThresh] = 0;
    a = np.sign(V).diff()
    segIn = a.index[a>0.5]-2/sf
    segOut = a.index[a<-0.5]
    
    # cut possible incomplete insp intervals at ends
    if segOut[0]<segIn[0]: 
        V.loc[:segOut[0]] = 0
        segOut = segOut[1:]
    if len(segOut)<len(segIn): 
        segIn = segIn[:len(segOut)]
    
    # cut intervales of increase chest stretch without zero crossings
    insp = insp[insp.index>segIn[0]]
    for j in range(len(segIn)):
        if len(insp.loc[segIn[j]:segOut[j]])<1:
            V.loc[segIn[j]:segOut[j]] = 0
    
    # define breath intervals on remaining increases
    a = np.sign(V).diff()
    segIn = a.index[a>0.5]
    segOut = a.index[a<-0.5]
    
    # cut possible incomplete insp intervals at ends again
    if segOut[0]<segIn[0]: 
        segOut = segOut[1:]
    if len(segOut)<len(segIn): 
        segIn = segIn[:len(segOut)]

    d = {'In': segIn,'Ex': segOut}
    Breaths = pd.DataFrame(data = d)
    return Breaths

def Breath_Features(sig,scalingfactor=0,filtered=False):
    ''' a function to extract breath-wise characteristics of chest expansion measurements
    taken on human adults without exertion or vocalisation (seated or standing still)
    It can evaluate raw recordings (with timestamp index) or preprocessed signals.
    
    Input:
        sig - evenly sampled (>=10 Hz) chest expansion recording of respiration
              as a Pandas Dataframe or Series with timestamps as floats in index
        scalingfactor - optional argument for setting the scaling constant for preprocessing
                signal with respnormed
              If blank or zero, the function scales by median inspiration velocity 
              If scalingfactor=1, the function preserves the input signal units (but sets average to 0)
              If scaling=C, the signal values are multiplied by the float C
        filtered - optional input (true false)
                optional argument for setting the scaling constant for preprocessing in respnormed
              If false (default), sig will passed to function respnormed
              If True, sig will evaluated directly, as its presumably been filtered
        
    Output:
        Breaths - many column dataframe reporting statistics on breaths 
              detected with Inspiration_Extract
              'In' - Sample time point closest to inspiration onset
              'Ex' - Sample time point closest to subsequent expiration onset
              'Depth' - signal value difference from 'In' and 'Ex'
              'Insp_T'- Duration from 'In' to 'Ex'
              'Period_T' - Duration to next 'In' (if it is in the signal)
              'Exp_T' - Duration from 'Ex' to next 'In' (if it is in the signal)
              'IE_Ratio' - Insp_T/Exp_T, usually a value between [0.2,1]
              'Insp_V' - Average velocity of inspiration (Depth/Insp_T)(usually a bit under mode)
              'Exp_V' - Average velocity of expiration (Depth/Exp_T) (usually over mode)
    
    Related libraries: 
    from scipy.signal import butter,filtfilt
    import numpy as np
    import pandas as pd
    local functions: respnormed, diffed,Inspiration_Extract
    '''
    # evaluate breath phase onsets with 
    # optional argument of scaling factor and filtering to prep signal
    newResp = pd.DataFrame(index = sig.index)
    if filtered:
        Breaths = Inspiration_Extract(sig,filtered=True)  
        newResp['Filt'] = sig
    else:
        Breaths = Inspiration_Extract(sig) 
        if not scalingfactor==0:
            newResp['Filt'] = respnormed(sig,scaling=scalingfactor)
        else:
            newResp['Filt'] = respnormed(sig)
   
    Breaths['Depth'] = newResp.loc[Breaths['Ex'].values,'Filt'].values-newResp.loc[Breaths['In'].values,'Filt'].values
    Breaths['Insp_T'] = Breaths['Ex'] - Breaths['In']
    a = Breaths['In'].diff()
    Breaths.loc[:len(Breaths)-2,'Period_T'] = a[1:].values
    Breaths['Exp_T'] = Breaths['Period_T'] - Breaths['Insp_T']
    Breaths['IE_Ratio'] = Breaths['Insp_T']/Breaths['Exp_T'] 
    Breaths['Insp_V'] = Breaths['Depth']/Breaths['Insp_T']
    Breaths['Exp_V'] = Breaths['Depth']/Breaths['Exp_T']

    return Breaths

def Breath_Continues_Features(sig,scaling=0,filtered=False,interp_style='previous'):
    ''' a function to output timeseries of breath-wise characteristics of chest expansion measurements
    taken on human adults without exertion or vocalisation (seated or standing still)
    It can evaluate raw recordings (with timestamp index) or preprocessed signals.
    
    Input:
        sig - evenly sampled (>=10 Hz) chest expansion recording of respiration
              as a Pandas Dataframe or Series with timestamps as floats in index
        scalingfactor - optional argument for setting the scaling constant for preprocessing
                signal with respnormed
              If blank or zero, the function scales by median inspiration velocity 
              If scalingfactor=1, the function preserves the input signal units (but sets average to 0)
              If scaling=C, the signal values are multiplied by the float C
        filtered - optional input (true false)
                optional argument for setting the scaling constant for preprocessing in respnormed
              If false (default), sig will passed to function respnormed
              If True, sig will evaluated directly, as its presumably been filtered
        interp_style - optional input (‘linear’, ‘nearest’, ‘zero’, ‘slinear’, ‘quadratic’, ‘cubic’, ‘previous’, ‘next’)
               specify the type of interpolation from breathwise to signal time series
               defauls is "previous" which caries the value per breath through it's duration
    Output:
        Breaths - many column dataframe reporting time series of breath characteristics
              detected with Inspiration_Extract. 
              Values are interpolated from inspiratin onset as that is the active phase is in these breaths
                  Except for Exp_T and Exp_V which interpolate on expiration onsets
              'Raw' - options raw signal input if also processing with respnorm
              'Filt' - filtered signal (may be input signal depending on settings)
              'Depth' - signal value difference from 'In' and 'Ex'
              'Insp_T'- Duration from 'In' to 'Ex'
              'Period_T' - Duration to next 'In' (if it is in the signal)
              'Exp_T' - Duration from 'Ex' to next 'In' (if it is in the signal)
              'IE_Ratio' - Insp_T/Exp_T, usually a value between [0.2,1]
              'Insp_V' - Average velocity of inspiration (Depth/Insp_T)(usually a bit under mode)
              'Exp_V' - Average velocity of expiration (Depth/Exp_T) (usually over mode)
    
    Related libraries: 
    from scipy.signal import butter,filtfilt
    import numpy as np
    import pandas as pd
    local functions: respnormed, diffed,Inspiration_Extract
    '''
    if filtered:
        Breaths = Breath_Features(sig,scalingfactor=scaling,filtered=True)
    else:
        Breaths = Breath_Features(sig,scalingfactor=scaling,filtered=False)
    cols = Breaths.columns
    
    # evaluate sampling parameters
    dt = np.nanmean(np.diff(sig.index))
    sf = round(1/dt)
    # creat parallel dataframe to input sig
    df_sig = pd.DataFrame(sig.values,index=sig.index)
    df_sig = df_sig.rename(columns={0:'Raw'})
    # remove nans (they sneak in)
    df_sig = df_sig.loc[df_sig['Raw'].notna()]-df_sig.loc[df_sig['Raw'].notna()].mean()
    
    #prep derivatives of respiration signal
    RespFeatures = pd.DataFrame(index = df_sig.index)
    if not filtered:
        RespFeatures ['Raw'] = df_sig['Raw']
        RespFeatures ['Filt'] = respnormed(RespFeatures ['Raw'],scaling=1)
    else:
        RespFeatures ['Filt'] = df_sig['Raw']

    for col in cols[2:]:
        if col.startswith('Ex'):
            f = interp1d(Breaths['Ex'],Breaths[col], kind='previous',fill_value='extrapolate')
        else:
            f = interp1d(Breaths['In'],Breaths[col], kind='previous',fill_value='extrapolate')
        RespFeatures[col]=f(RespFeatures.index)

    return RespFeatures