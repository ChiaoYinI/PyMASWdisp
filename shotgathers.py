"""
    Classes:
        ShotGather: 
        Stores all of the relevent information for a given source-offset (i.e.,
        data acquisition parameters and time histories). The class has a number
        methods, which can print the attributes of the class, cut the time 
        histories, and plot the time histories.

    Functions:
        importAndStackWaveforms: 
        Import and stack data (from seg2 files) for a given source-offset  
        
        calcSNR:
        Calculate signal-to-noise ratios for a given source-offset

        compareSNR:
        Plot/compare signal-to-noise ratios   

        create_ColorMap:
        Create an array of RGB colors associated with a colormap (e.g., jet)    


    This code was developed at the University of Texas at Austin.
    Copyright (C) 2016  David P. Teague, Clinton M. Wood, and Brady R. Cox 
 
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
 
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
 
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""


# Import modules
import numpy as np
from scipy import signal
import tkinter as tk
import matplotlib.colors as colors
import matplotlib.cm as cmx
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FormatStrFormatter
from obspy import read
import os


# Class to store time histories and associated data acquisition parameters
class ShotGather(object):
    
    # Class attributes
    def __init__(self, dt, n_channels, n_samples, position, offset, delay, timeHistories):
        self.dt = dt
        self.n_channels = n_channels
        self.n_samples = n_samples
        self.position = position
        self.offset = offset
        self.delay = delay
        self.timeHistories = timeHistories
        self.multiple = 1 # Used when zeros are padded such that down-sampling every "multiple" samples is necessary

    # Method to print attributes of time histories
    def print_attributes(self):
        print " "
        print "Shot Gather:"
        print "dt:          "+str(self.dt)
        print "n_channels:  "+str(self.n_channels)
        print "n_samples:   "+str(self.n_samples)
        print "position:    "+str(self.position[0])+", "+str(self.position[1])+", ...,"+str(self.position[len(self.position)-1])
        print "offset:      "+str(self.offset)
        print "delay:       "+str(self.delay)
        print "timeHistories"+str(np.shape(self.timeHistories))

    # Method to cut waveforms
    def cut(self, max_time, newDelay=0):
        time = np.arange(self.delay, (self.n_samples*self.dt + self.delay), self.dt)
        # Keep entire pretrigger delay
        if newDelay=='full':
            startID = 0
        # Remove all data before time = newDelay (default is to remove all data before t=0)
        else:
            self.delay = -np.abs( float(newDelay) )
            startID = np.where( np.abs(time-self.delay) == np.min(np.abs(time-self.delay)) )[0][0]
        endID = np.where( np.abs(time-max_time) == np.min(np.abs(time-max_time)) )[0][0]+1
        time = time[startID:endID]
        self.n_samples = len(time)
        self.timeHistories = self.timeHistories[startID:endID][:]
        return

    # Method to plot waveforms
    def plot(self, scale_factor=1, plot_ax='x'):
        time = np.arange(self.delay, (self.n_samples*self.dt + self.delay), self.dt)
        # Normalize and detrend
        norm_traces = np.zeros( np.shape(self.timeHistories) )
        for k in range(self.n_channels):
            current_trace = self.timeHistories[:,k]
            current_trace = signal.detrend(current_trace)                   # Linear detrend
            current_trace = current_trace / np.amax(current_trace)          # Normalize by max value
            current_trace = current_trace*scale_factor + self.position[k]   # Scale and shift
            norm_traces[:,k]= current_trace

        # Set figure size equal to 2/3 screen size
        # Get screen size in mm and convert to in (25.4 mm per inch)
        root = tk.Tk()
        width = root.winfo_screenmmwidth() / 25.4 * 0.66
        height = root.winfo_screenmmheight() / 25.4 * 0.66
        fig = plt.figure( figsize=(width,height) )

        # Plotting
        ax = fig.add_subplot(111)
        ax.hold(True)
        for m in range(self.n_channels):
            ax.plot(time, norm_traces[:,m],'b-')
        ax.set_xlim( ( min(time), max(time) ) )
        ax.set_ylim( (-self.position[1], self.position[1]+self.position[len(self.position)-1] ) )
        ax.grid(axis='x', linestyle='--')
        ax.set_xlabel('Time (s)', fontsize=14, fontname="arial")
        ax.set_ylabel('Normalized Amplitude', fontsize=14, fontname="arial")
        ax.tick_params(labelsize=14)
        ax.tick_params('x', length=10, width=1, which='major')
        ax.tick_params('y', length=10, width=1, which='major')
        plt.show()
        return 

    # Method to padd zeros to acheive desired frequency sampling
    def zero_pad(self, df = 0.2):
        # Required length of time history for desired df
        n_req = int(np.round( 1/(df*self.dt) )) 
        # If n_req > n_samples, padd zeros to achieve n_samples = n_req
        if n_req > self.n_samples:
            self.timeHistories = np.concatenate( ( self.timeHistories, np.zeros((n_req - self.n_samples,self.n_channels)) ), axis=0 )
            self.n_samples = n_req
        # If n_req < n_samples, padd enough zeros to achieve a fraction of df (df/2, df/4, etc.)
        # After processing, the results at the frequencies of interest can be extracted
        else:
            # Multiples of df and n_req
            multiples = np.array( [2, 4, 8, 16, 32], int )
            trial_n = n_req * multiples
            # Find first trial_n > n_req
            nextIDs = np.where( self.n_samples < trial_n )
            nextID = nextIDs[0][0]
            self.multiple = multiples[nextID] 
            # Pad zeros
            self.timeHistories = np.concatenate( ( self.timeHistories, np.zeros((trial_n[nextID] - self.n_samples,self.n_channels)) ), axis=0 )
            self.n_samples = trial_n[nextID]
        return        
   
     

# Function for importing and stacking waveforms
# Stacked waveforms are saved as a ShotGather class
def importAndStackWaveforms( start_file, end_file, file_path=os.getcwd(), exclude_files=[], print_status='yes' ):

    # Import data from first seg2 file
    waveforms = read( file_path+"/"+str(start_file)+".dat", 'seg2' ) 

    # Determine acquisition parameters
    dt = waveforms[0].stats.delta    
    n_channels = int( len( waveforms ) )
    n_samples = int( waveforms[0].stats.npts )
    offset = float( waveforms[0].stats.seg2['RECEIVER_LOCATION']) - float(waveforms[0].stats.seg2['SOURCE_LOCATION']) 
    delay = float( waveforms[0].stats.seg2['DELAY'] )
    position = np.zeros(n_channels)
    for rec in range(1,n_channels):
        spacing = abs( float( waveforms[rec].stats.seg2['RECEIVER_LOCATION']) - float(waveforms[rec-1].stats.seg2['RECEIVER_LOCATION'] ) )
        position[rec] = position[rec-1] + spacing
        
    # Initialize variables
    timeHistories = np.zeros((n_channels, n_samples))
    indvTimeHist = np.zeros((n_channels, n_samples))

    # Import time histories and perform stacking
    # (time histories are imported as row vectors)
    n_files = 0
    for cfile in range( start_file, end_file+1 ):
        # Ensure that file exists and that it's not in the list of excluded files
        if os.path.isfile( file_path+"/"+str(cfile)+".dat" ) and (not (cfile in exclude_files)):
            if print_status=='yes':
                print "Importing file: "+str(cfile)+".dat"
            n_files += 1
            if cfile > start_file:
                waveforms = read( file_path+"/"+str(cfile)+".dat", 'seg2' ) 
            for k in range(0, n_channels):
                indvTimeHist[k][:] = waveforms[k]
            timeHistories += indvTimeHist
        else:
            print "WARNING: File named "+str(cfile)+".dat does not exist or was omitted from the analysis."
    
    # Transpose so that matrix is (n_samples x n_channels)
    timeHistories = np.transpose( timeHistories )/n_files
    # If necessary, flip timeHistories from left to right
    if offset<0:
        timeHistories = np.fliplr( timeHistories )
        offset = position[::-1][0]+offset

    # Create instance of ShotGather class and print summary
    shotgather = ShotGather(dt, n_channels, n_samples, position, offset, delay, timeHistories)
    if print_status=='yes':
        shotgather.print_attributes()
    return shotgather



# Function for calculating and plotting signal-to-noise ratio (SNR)
def calcSNR( shotGather, timelength=1, noise_location='end', df=0.2, plotSNR=False, xscale='linear' ):

    # Time vector
    time = np.arange(shotGather.delay, (shotGather.n_samples*shotGather.dt + shotGather.delay), shotGather.dt)
    
    # Signal time ( 0 <= time <= timelength )
    startpointS = int( np.argmin( abs(time - 0.0) ) )
    endpointS = int( startpointS + timelength/shotGather.dt )
    # Noise time (delay <= time <= delay+timelength) or (t_end - timelength <= time <= t_end, where t_end is the end time of the record)
    if str.lower(noise_location)=='end':
        endpointN = len(time)-1
        startpointN = int( endpointN - timelength/shotGather.dt )
    elif str.lower(noise_location)=='pretrigger':
        startpointN = int( np.argmin( time-shotGather.delay ) )
        endpointN = int( startpointN + timelength/shotGather.dt )
    else:
        raise ValueError("Invalid noise_location. Should be \"end\" or \"pretrigger\".") 

    # Verify that signal and noise records do not overlap. If they do, return an error
    if (endpointS > startpointN) and (str.lower(noise_location)=='end'):
        raise Exception( 'Error: Signal and noise records are overlapping' ) 
    elif (endpointN > startpointS) and (str.lower(noise_location)=='pretrigger'):
        raise Exception( 'Error: Signal and noise records are overlapping' )
    # Verify that signal and noise records are each equal to timeLength
    if ( (time[endpointS]-time[startpointS]) < timelength ):
        raise Exception( 'Error: Signal record length is less than timelength' )
    elif ( (time[endpointN]-time[startpointN]) < timelength ):
        raise Exception( 'Error: Noise record length is less than timelength' )

    # Create instances of ShotGather class for signal and noise
    shotGatherS = ShotGather(shotGather.dt, shotGather.n_channels, (endpointS-startpointS+1), shotGather.position, shotGather.offset, time[startpointS], shotGather.timeHistories[startpointS:endpointS+1,:])
    shotGatherN = ShotGather(shotGather.dt, shotGather.n_channels, (endpointN-startpointN+1), shotGather.position, shotGather.offset, time[startpointN], shotGather.timeHistories[startpointN:endpointN+1,:])
    # Pad zeros to acheive desired frequency sampling
    shotGatherS.zero_pad(df)
    shotGatherN.zero_pad(df)
    
    # Sampling paramters
    fnyq = 1/(2*shotGatherS.dt)
    df = 1/(shotGatherS.n_samples*shotGatherS.dt)
    freq = np.arange(df, fnyq, df)

    # Perform FFT on signal and noise records
    fftS = np.fft.fft( shotGatherS.timeHistories, axis=0 )
    fftN = np.fft.fft( shotGatherN.timeHistories, axis=0 )

    # Average signal and noise amplitudes (remove f=0 and negative frequencies)
    ampS = (2.0/shotGatherS.n_samples) * np.abs( fftS[1:len(freq)+1] )
    meanAmpS = np.mean( ampS, axis=1 )
    ampN = (2.0/shotGatherN.n_samples) * np.abs( fftN[1:len(freq)+1] )
    meanAmpN = np.mean( ampN, axis=1 )

    # Compute SNR = 20*log10( signal_amplitude / noise_amplitude )
    SNR = 20 * np.log10( meanAmpS / meanAmpN )

    # Plotting
    if plotSNR:
        # Set figure size equal to 2/3 screen size
        # Get screen size in mm and convert to in (25.4 mm per inch)
        root = tk.Tk()
        width = root.winfo_screenmmwidth() / 25.4 * 0.66
        height = root.winfo_screenmmheight() / 25.4 * 0.66
        fig = plt.figure( figsize=(width,height) )  
        ax = fig.add_axes([0.1, 0.08, 0.85, 0.88])
        ax.hold(True) 
        ax.plot( freq, SNR, '-', linewidth=2 )  
        ax.set_xlabel('Frequency (Hz)', fontsize=14, fontname='arial')
        ax.set_ylabel('Signal-to-Noise Ratio (dB)', fontsize=14, fontname='arial')
        ax.set_xscale(xscale)
        ax.set_yscale('linear')
        ax.set_xticklabels(ax.get_xticks(), fontsize=14, fontname='arial' )
        ax.set_yticklabels(ax.get_yticks(), fontsize=14, fontname='arial' )
        fig.show()

    return (SNR, freq)




# Function to plot/compare signal-to-noise ratios
def compareSNR( infile_numbers, infile_path=os.getcwd(), noise_location='end', timelength=1, exclude_files=[], deltaf=0.2 ):
    
    # Colors of stacked SNR curves
    plotColorsStack = create_ColorMap( len(infile_numbers) )

    # Set figure size equal to 2/3 screen size
    # Get screen size in mm and convert to in (25.4 mm per inch)
    root = tk.Tk()
    width = root.winfo_screenmmwidth() / 25.4 * 0.66
    height = root.winfo_screenmmheight() / 25.4 * 0.66
    fig = plt.figure( figsize=(width,height) )

    # Additional plotting parameters    
    ax = fig.add_axes([0.1, 0.08, 0.85, 0.88]) 
    ax.set_xscale('linear')
    ax.set_yscale('linear')
    ax.set_xlim( (0, 50) )
    ax.set_xticklabels(ax.get_xticks(), fontsize=14, fontname='arial' )
    ax.set_yticklabels(ax.get_yticks(), fontsize=14, fontname='arial' )
    ax.xaxis.set_major_locator( MultipleLocator(10) )
    ax.xaxis.set_major_formatter( FormatStrFormatter('%d') )
    ax.yaxis.set_major_formatter( FormatStrFormatter('%d') )
    ax.xaxis.set_minor_locator( MultipleLocator(2) )
    ax.yaxis.set_minor_locator( MultipleLocator(2) )
    ax.tick_params('both', length=10, width=1, which='major')
    ax.tick_params('both', length=5, width=1, which='minor') 
    ax.hold(True)
    ax.set_xlabel('Frequency (Hz)', fontsize=14, fontname='arial')
    ax.set_ylabel('Signal-to-Noise Ratio (dB)', fontsize=14, fontname='arial')
    yMax = 0
    
    
    # Loop through offset(s) and plot signal-to-noise ratio
    for m in range( len(infile_numbers) ):
    
        # If only one offset is chosen, show SNR for individual shots...........

        # Determine total number of files minus excluded files
        if len(infile_numbers)==1:
            # Determine total number of files minus excluded files
            Nf = 0
            Nt = 0
            freqRange = []
            for k in range( infile_numbers[m][0], infile_numbers[m][1]+1 ):
                Nt += 1
                if not (k in exclude_files):
                    Nf += 1
                    freqRange.append(k)

            # Colors associated with individual files
            plotColorsIndv = create_ColorMap(Nf)

            # Calculate individual SNR, plot results
            for k in range(Nf):
                shotGather = importAndStackWaveforms( freqRange[k], freqRange[k], infile_path, [], 'no' )
                SNR, freq = calcSNR( shotGather, timelength, noise_location, deltaf )
                ax.plot( freq, SNR, '-', color=plotColorsIndv[k,:], linewidth=1, label=str(k)+'.dat' )
    

        # Plot SNR for stacked shot(s)
        shotGather = importAndStackWaveforms( infile_numbers[m][0], infile_numbers[m][1], infile_path, exclude_files, 'no' )
        SNR, freq = calcSNR( shotGather, timelength, noise_location, deltaf )
        if len(infile_numbers)==1:
            ax.plot( freq, SNR, '-', color='black', linewidth=2.5, label='Stacked: '+str(shotGather.offset)+' m Offset' )
        else:
            clabel = str(shotGather.offset)+' m Offset'
            ax.plot( freq, SNR, '-', color=plotColorsStack[m,:], linewidth=2.5, label=clabel )
    
        # Determine appropriate maximum for y-axis
        while yMax < np.max(SNR):
            yMax += 10
    
    ax.legend(loc='upper left')
    ax.set_ylim( (0, yMax) )
    fig.show()



# Create an array, where each row contains an RGBA color equally spaced in a colormap
def create_ColorMap( N, maptype='jet' ):
    ccmap = plt.get_cmap( maptype ) 
    cNorm  = colors.Normalize(vmin=0, vmax=(N-1))
    scalarMap = cmx.ScalarMappable(norm=cNorm, cmap=ccmap)
    plotColors = np.zeros( (N,4) )
    for k in range( N ):
        plotColors[k,:] = scalarMap.to_rgba( k )
    return plotColors