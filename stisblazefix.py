#Created by Malinda Baer on June 20, 2017
#based on IDL routines written by Charles Proffitt
#
#This module is written in Python 3.6.1
#
#This module contains required functions for the following scripts:
#
#This module requires:
#numpy, scipy, astropy, matplotlib, lmfit, time
#
#NOTE: requires at least numpy 1.13, bugs occur with numpy 1.12
#
#Import using the command "import stisfix"
#

'''This module contains a variety of functions to correct the blaze function in HST STIS
echelle modes. It is intended for use with x1d fits files. Most users will be interested 
in the fluxfix function.

fluxcorrect takes a shift to the blaze function and recalculates the flux and error.
residcalc takes an echelle spectrum and calculates the flux residuals for the overlapping region.
generateplot takes an old and corrected spectrum and generates a diagnostic plot.
residfunc is a wrapper for lmfit minimizer.
findshift calculates the shift to the blaze function that best aligns the spectrum.
fluxfix takes a list of x1d fits files and generates corrected x1f files and diagnostic plots.
plotblaze plots the sensitivity curves for an extracted spectra.
'''

from astropy.io import fits
import numpy as np
from numpy import ma
from scipy import interpolate
from matplotlib.backends.backend_pdf import PdfPages
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.text as txt
from lmfit import Parameters, Minimizer, conf_interval, minimize, printfuncs
import time

stis_flags = {'Reed-Solomon': 1, 'fill_vals': 2, 'detector_pix': 4, 'occulting_bar': 8, 'high_dark': 16, 'large_blemish': 32, 'vignetted': 64, 'overscan': 128, 'saturated': 256, 'ref_pixel': 512, 'small_blemish': 1024, 'background': 2048, 'bad_input': 4096, 'cosmic_ray': 8192, 'negative': 16384}
#full description of dq flags in STIS data handbook

default_flags = [32, 64]

def datamask(array, dq, flags=default_flags):
    '''Mask data with bad dq flags.
    
    array is the array to be masked.
    dq is the corresponding dq array.
    flags contains the dq values to mask.
'''
    badflags = 0
    for item in flags:
        badflags += item
    if badflags = 0:
        print('Warning: no dq flags selected.')
    index = np.where(dq & badflags)
    #continue fixing


def fluxcorrect(filedata, pixshift):
    '''Recalculate and return corrected flux and error vectors, based on shifted blaze function.
    
    filedata is the data attribute of an x1d fits file.
    
    pixshift is a 1D vector with length equal to the number of orders in the echelle spectrum.
    It contains the shift of the blaze function in pixels as a function of relative spectral order.
    '''
    #add checks in main, or here? Probably in here, but could do in both
    #still need to check for zero division?
    origblaze = np.divide(filedata['net'], filedata['flux'])#back out original sensitivity
    shape = np.shape(origblaze)
    newblaze = np.zeros(shape)
    order = 0
    pixnos = np.arange(shape[1])#shape[1] should always be 1024 for STIS
    while order < shape[0]:#number of orders
        f = interpolate.interp1d(pixnos, origblaze[order], fill_value='extrapolate')#
        newblaze[order] = f(pixnos - pixshift[order])#shifts the blaze function
        order += 1
    newflux = np.divide(filedata['net'], newblaze)
    newerr = np.divide(filedata['net_error'], newblaze)
    return (newflux, newerr)

def residcalc(filedata, flux=None, err=None, ntrim=5):
    '''Calculate and return the flux overlap residuals and weighted error.
    
    Flux residuals are calculated by summing the flux in the overlapping region in adjacent orders,
    taking the ratio, and subtracting from one.
    
    filedata is the data attribute of an x1d fits file.
    
    kwargs:
    flux is a flux vector the same size as the flux in filedata.
    erre is an error vector the same size as the error rin filedata.
    If either flux or error is passed, they will be used to calculate the residuals.
    Otherwise, the flux and error from filedata will be used.
    ntrim is a cut made to the edges of the orders to avoid various edge problems. Defaults to 5.
    '''
    if flux is None:
        flux = filedata['flux']
    if err is None:
        err = filedata['error']
    wavelength = filedata['wavelength']
    shape = np.shape(flux)
    resids = np.zeros(shape[0] - 1)#one less residual than orders
    residerr = np.zeros(np.shape(resids))
    order = 0
    while order < (shape[0] - 1):
        #make cut before interpolating
        f = interpolate.interp1d(wavelength[order + 1], flux[order + 1], fill_value='extrapolate')
        g = interpolate.interp1d(wavelength[order + 1], err[order + 1], fill_value='extrapolate')
        overlap = np.where(wavelength[order] <= wavelength[order + 1][-1])
        #can do some trimming here
        f0 = flux[order][overlap]
        f1 = f(wavelength[order][overlap])#interpolate to the same wavelength bins
        g0 = err[order][overlap]
        g1 = g(wavelength[order][overlap])
        fluxsum0, fluxsum1 = 0, 0#sum of flux in overlap regions for order and order+1 
        errsum0, errsum1 = 0, 0#hold error sums
        #trim edges and outliers
        i=ntrim
        while i < np.shape(overlap)[1] - ntrim:
            fluxsum0 += f0[i]
            fluxsum1 += f1[i]
            errsum0 += g0[i] **2
            errsum1 += g1[i] **2
            i += 1
        try:
            resid = 1 - fluxsum0/fluxsum1
            residerr[order] = abs(1 - resid) * np.sqrt(errsum0/(fluxsum0**2) + errsum1/(fluxsum1**2))
        except ZeroDivisionError:
            resid = 0
            residerr[order] = 1
        resids[order] = resid
        order += 1
    return (resids, residerr)

def generateplot(origdata, newflux, newerr, pixshift, oldresids=None, olderr=None, ntrim=5):
    '''Generate a diagnostic plot for a corrected spectrum. 
    
    Plot spectrum and residuals before and after correction to blaze function, 
    and pixshift vs relative spectral order.
    Return a figure object.
    
    origdata is the data attribute of an x1d fits file. This should contain the original flux.
    newflux contains the corrected flux.
    newerr contains the corrected error.
    pixshift is a 1D vector with length equal to the number of orders in the echelle spectrum.
    
    kwargs:
    oldresids contains the residuals for the uncorrected data.
    olderr contains the error in the residuals for the uncorrected data.
    If neither is passed, they will be calculated from origdata.
    ntrim is a cut made to the edges of the orders to avoid various edge problems. Defaults to 5.
    '''
    origflux = origdata['flux']
    wavelength = origdata['wavelength']
    shape = np.shape(origflux)#(no. orders, no. pixels)
    
    if oldresids is None or olderr is None:
        old = residcalc(origdata)
        if oldresids is None:
            oldresids = old[0]
        if olderr is None:
            olderr=old[1]
    newresids, newresiderr = residcalc(origdata, flux=newflux, err=newerr)
    
    fig = plt.figure(figsize=(10,7))
    gs = gridspec.GridSpec(2, 2, width_ratios=[5,2])

    oldspec = plt.subplot(gs[0])#spectrum before correction
    order = 0
    while order < shape[0]:
        plt.plot(wavelength[order][ntrim:-(ntrim+1)], origflux[order][ntrim:-(ntrim+1)], lw=0.1, alpha=0.3)
        order += 1
    plt.title('Spectrum Before Correction')
    plt.xlabel('Wavelength (Angstroms)')
    plt.ylabel('Flux (erg/s/cm^2/Angstrom)')
    
    newspec = plt.subplot(gs[2], sharex=oldspec, sharey=oldspec)#spectrum after correction
    order = 0
    while order < shape[0]:
        plt.plot(wavelength[order][ntrim:-(ntrim+1)], newflux[order][ntrim:-(ntrim+1)], lw=0.1, alpha=0.3)
        order += 1
    plt.title('Spectrum After Correction')
    plt.xlabel('Wavelength (Angstroms)')
    plt.ylabel('Flux (erg/s/cm^2/Angstrom)')
    
    residplot = plt.subplot(gs[1])#residuals before and after correction vs spectral order
    before = plt.errorbar(np.arange(np.shape(oldresids)[0]), oldresids, yerr=olderr, fmt='o', markersize=2, alpha=0.6)
    after = plt.errorbar(np.arange(np.shape(newresids)[0]), newresids, yerr=newresiderr, fmt='o', markersize=2, alpha=0.6)
    plt.plot(np.arange(np.shape(newresids)[0]), np.zeros(np.shape(newresids)[0]), '-')
    plt.ylabel('1 - Flux Ratio')
    plt.xlabel('Relative Spectral Order')
    plt.title('Flux Overlap')
    plt.legend([before, after], ['Before Correction', 'After Correction'])
    
    pixplot = plt.subplot(gs[3], sharex=residplot)#graph of pixshift v spectral order
    plt.plot(pixshift, 'o', markersize=2)
    plt.title('Pixshift')
    plt.xlabel('Relative Spectral Order')
    plt.ylabel('Shift in Pixels')
    #if params is not None:
    #    txt.text('a + b*x'#check that call

    return fig

def residfunc(pars, x, filedata):#function for lmfit - is there way to add loop for linear/0th/quadratic? - try adjusting number of parameters
    '''Wrapper for lmfit minimizer. 
    
    Return weighted residuals for a given pixshift.
    
    pars is a tuple containing lmfit parameters.
    x is the variable, in this case relative spectral order.
    filedata is the data attribute of an x1d fits file.
    '''
    a = pars['a'].value
    b = pars['b'].value
    pixshift = a + b*x
    new = fluxcorrect(filedata, pixshift)
    newflux = new[0]
    newerr = new[1]
    temp = residcalc(filedata, flux=newflux, err=newerr)#(resid, residerr)
    wresids = np.abs(np.divide(temp[0], temp[1]))#weighted resid = resid/sig
    return wresids
    
def findshift(filedata, guess, iterate=True):
    '''Find pixshift that best aligns spectral orders.
    
    Use lmfit to calculate the pixshift (to apply to the blaze function) as a linear 
    function of relative spectral order that minimizes the flux overlap residuals
    as calculated in residcalc.
    
    Return pixshift, the error in the pixshift, and the final parameters.
    
    filedata is the data attribute of an x1d fits file.
    guess is a tuple containing the starting parameters for the fit.
    iterate is a Boolean that determines whether the function iterates to find the best fit.
    '''
    x = np.arange(np.shape(filedata)[0])
    params = Parameters()
    params.add('a', value=guess[0])
    params.add('b', value=guess[1])
    if !iterate:
        params['a'].vary, params['b'].vary = False, False
    min = minimize(residfunc, params, args=(x, filedata))
    #include diagnostics and throw warnings
    a = (min.params['a'].value, min.params['a'].stderr)
    b = (min.params['b'].value, min.params['b'].stderr)
    pixshift = a[0] + (b[0])*x
    pixerr = np.sqrt(a[1]**2 + (x * b[1])**2)
    return (pixshift, pixerr, (a, b))
    

def fluxfix(files, pdfname, guess=None, iterate=True **kwargs):#add optional arguments for plotting, eg. files is a list of x1d fits spectra
    '''Corrects a list of echelle spectra by aligning the spectral orders.
    
    Take a list of x1d fits files, and for each spectrum find the shift to the blaze 
    function that best aligns the orders in the spectrum, recalculate the flux with that
    blaze function, create an x1f fits file with the new flux and error, and generate 
    a diagnostic plot. This creates a new fits file for each one in files, and one
    pdf file containing the diagnostic plots.
    
    files is a list or tuple of x1d fits files.
    pdfname is the name of the pdf file that will be generated. This name must be unique.
    guess is the starting parameters for pixshift, in the form (a, b) -> a + b*x 
    iterate is a Boolean that determines whether fluxfix iterates or only uses the starting guess.
    Takes keyword arguments.
    '''
    if guess is None:
        guess=(1, 0.5)
    pdf = PdfPages(pdfname)
    for filename in files:
        file = fits.open(filename)
        extno = len(file)
        i = 1
        while i < extno:#for i, extension in enumerate(file, start=1):#while i < extno:
            filedata = file[i].data
            shift = findshift(filedata, guess)
            pixshift, pixerr, params = shift[0], shift[1], shift[2]
            new = fluxcorrect(filedata, pixshift)
            newflux, newerr = new[0], new[1]
            graph = generateplot(filedata, newflux, newerr, pixshift)
            plt.suptitle(filename[:-9] + ' Extension: ' + str(i))
            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            pdf.savefig()
            i += 1
        hdr = file[0].header
        hdr['comment'] = 'Spectra corrected using stisfix on ' + time.strftime('%d/%m/%Y')
        filedata['flux'] = newflux
        filedata['error'] = newerr
        try:
            file.writeto(filename[:-6] + 'f.fits')
        except OSError:
            i = 1
            while True:
                try:
                    file.writeto(filename[:-6] + 'f' + str(i) + '.fits')
                    break
                except OSError:
                    i += 1
        file.close()
    pdf.close()

def plotblaze(filename, pdfname, ntrim=7):
    '''Plot the blaze function for each order of a STIS echelle spectrum.'''
    pdf = PdfPages(pdfname)
    file = fits.open(filename)
    fig = plt.figure()
    extno = len(file)
    i = 1
    while i < extno:
        filedata = file[i].data
        wavelength = filedata['wavelength']
        flux = filedata['flux']
        net = filedata['net']
        blaze = net/flux
        shape = np.shape(wavelength)
        order = 0
        while order < shape[0]:
            plt.plot(wavelength[order], blaze[order], lw=0.05)
            order += 1
        plt.title('Blaze Function')
        plt.xlabel('Wavelength (Angstroms)')
        plt.ylabel('Relative Intensity')
        plt.suptitle(filename[:-9] + ' Extension: ' + str(i))
        pdf.savefig()
        i += 1
    file.close()
    pdf.close()
        
