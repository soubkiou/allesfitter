#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  5 01:03:21 2018

@author:
Maximilian N. Günther
MIT Kavli Institute for Astrophysics and Space Research, 
Massachusetts Institute of Technology,
77 Massachusetts Avenue,
Cambridge, MA 02109, 
USA
Email: maxgue@mit.edu
Web: www.mnguenther.com
"""

from __future__ import print_function, division, absolute_import

#::: modules
import numpy as np
import os
import emcee
from multiprocessing import Pool
from contextlib import closing

#::: warnings
import warnings
warnings.filterwarnings('ignore', category=np.VisibleDeprecationWarning) 
warnings.filterwarnings('ignore', category=np.RankWarning) 

#::: allesfitter modules
from . import config
from .computer import update_params,\
                      calculate_lnlike
from .general_output import logprint
from .mcmc_output import print_autocorr



###############################################################################
#::: MCMC log likelihood
###############################################################################
def mcmc_lnlike(theta):
    
    params = update_params(theta)
    lnlike = 0
    
    for inst in config.BASEMENT.settings['inst_phot']:
        lnlike += calculate_lnlike(params, inst, 'flux')
    
    for inst in config.BASEMENT.settings['inst_rv']:
        lnlike += calculate_lnlike(params, inst, 'rv')

    return lnlike

    
        
###############################################################################
#::: MCMC log prior
###############################################################################
def mcmc_lnprior(theta):
    '''
    bounds has to be list of len(theta), containing tuples of form
    ('none'), ('uniform', lower bound, upper bound), or ('normal', mean, std)
    '''
    lnp = 0.        
    
    for th, b in zip(theta, config.BASEMENT.bounds):
        if b[0] == 'uniform':
            if not (b[1] <= th <= b[2]): return -np.inf
        elif b[0] == 'normal':
            lnp += np.log( 1./(np.sqrt(2*np.pi) * b[2]) * np.exp( - (th - b[1])**2 / (2.*b[2]**2) ) )
        else:
            raise ValueError('Bounds have to be "uniform" or "normal". Input from "params.csv" was "'+b[0]+'".')
    return lnp



###############################################################################
#::: MCMC log probability
###############################################################################    
def mcmc_lnprob(theta):
    '''
    has to be top-level for  for multiprocessing pickle
    '''
    lp = mcmc_lnprior(theta)
    if not np.isfinite(lp):
        return -np.inf
    else:
        try:
            ln = mcmc_lnlike(theta)
            return lp + ln
        except:
            return -np.inf
        


###########################################################################
#::: MCMC fit
###########################################################################
def mcmc_fit(datadir):
    
    #::: init
    config.init(datadir)
    
    
    continue_old_run = False
    if os.path.exists(os.path.join(config.BASEMENT.outdir,'mcmc_save.h5')):
        overwrite = str(input(os.path.join(config.BASEMENT.outdir,'mcmc_save.h5')+\
                              ' already exists.\n'+\
                              'What do you want to do?\n'+\
                              '1 : overwrite the save file\n'+\
                              '2 : append to the save file\n'+\
                              '3 : abort\n'))
        if (overwrite == '1'):
            continue_old_run = False
        elif (overwrite == '2'):
            continue_old_run = True
        else:
            raise ValueError('User aborted operation.')
            
    
    #::: set up a backend
    backend = emcee.backends.HDFBackend(os.path.join(config.BASEMENT.outdir,'mcmc_save.h5'))
    
    
    #::: continue on the backend / reset the backend
    if not continue_old_run:
        backend.reset(config.BASEMENT.settings['mcmc_nwalkers'], config.BASEMENT.ndim)
    
    
    #::: helper fct
    def run_mcmc(sampler):
        
        #::: set initial walker positions
        if continue_old_run:
            p0 = backend.get_chain()[-1,:,:]
            already_completed_steps = backend.get_chain().shape[0] * config.BASEMENT.settings['mcmc_thin_by']
        else:
            p0 = config.BASEMENT.theta_0 + config.BASEMENT.init_err * np.random.randn(config.BASEMENT.settings['mcmc_nwalkers'], config.BASEMENT.ndim)
            already_completed_steps = 0
        
        #::: make sure the inital positions are within the limits
        for i, b in enumerate(config.BASEMENT.bounds):
            if b[0] == 'uniform':
                p0[:,i] = np.clip(p0[:,i], b[1], b[2]) 
        
        #::: run the sampler        
        sampler.run_mcmc(p0,
                         (config.BASEMENT.settings['mcmc_total_steps'] - already_completed_steps)/config.BASEMENT.settings['mcmc_thin_by'], 
                         thin_by=config.BASEMENT.settings['mcmc_thin_by'], 
                         progress=True)
        
        return sampler


    #::: Run
    logprint("\nRunning MCMC...")
    logprint('--------------------------')
    if config.BASEMENT.settings['multiprocess']:
         with closing(Pool(processes=(config.BASEMENT.settings['multiprocess_cores']))) as pool: #multiprocessing
#        with closing(Pool(cpu_count()-1)) as pool: #pathos
            logprint('\nRunning on', config.BASEMENT.settings['multiprocess_cores'], 'CPUs.')
            sampler = emcee.EnsembleSampler(config.BASEMENT.settings['mcmc_nwalkers'], 
                                            config.BASEMENT.ndim, 
                                            mcmc_lnprob,
                                            pool=pool, 
                                            backend=backend)
            sampler = run_mcmc(sampler)
    else:
        sampler = emcee.EnsembleSampler(config.BASEMENT.settings['mcmc_nwalkers'],
                                        config.BASEMENT.ndim,
                                        mcmc_lnprob,
                                        backend=backend)
        sampler = run_mcmc(sampler)
    

    #::: Check performance and convergence
    logprint('\nAcceptance fractions:')
    logprint('--------------------------')
    logprint(sampler.acceptance_fraction)
    
    print_autocorr(sampler)
    
    