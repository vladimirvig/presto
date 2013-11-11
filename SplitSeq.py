#!/usr/bin/env python
"""
Converts, sorts, samples and splits FASTA/FASTQ sequence files
"""

__author__    = 'Jason Anthony Vander Heiden'
__copyright__ = 'Copyright 2013 Kleinstein Lab, Yale University. All rights reserved.'
__license__   = 'Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported'
__version__   = '0.4.1'
__date__      = '2013.10.12'

# Imports
import os, sys
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict
from random import sample
from time import time
from Bio import SeqIO

# IgCore imports
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from IgCore import default_coord_choices, default_coord_type, default_out_args
from IgCore import getAnnotationValues, parseAnnotation, indexSeqPairs, subsetSeqIndex
from IgCore import getCommonArgParser, parseCommonArgs
from IgCore import getOutputHandle, printLog, printProgress
from IgCore import countSeqFile, readSeqFile, getFileType


def convertSeqFile(seq_file, out_format, out_args=default_out_args):
    """
    Splits a FASTA/FASTQ file into segments with a limited number of records

    Arguments: 
    seq_file = filename of the FASTA file to split
    out_format = a list of formats to convert seq_file to
    out_args = common output argument dictionary from parseCommonArgs

    Returns: 
    a list of output file names
    """
    log = OrderedDict()
    log['START'] = 'SplitSeq'
    log['COMMAND'] = 'convert'
    log['FILE'] = os.path.basename(seq_file)
    printLog(log)
    
    # Convert records for each output file type
    out_files = []
    for out_type in out_format:
        seq_iter = readSeqFile(seq_file)
        with getOutputHandle(seq_file, None, out_dir=out_args['out_dir'], 
                             out_name=out_args['out_name'], out_type=out_type) \
                as out_handle:
            # Write sequences
            count = SeqIO.write(seq_iter, out_handle, out_type)
            out_files.append(out_handle.name)
            
            # Print log for iteration
            log = OrderedDict()
            log['FORMAT'] = out_type
            log['SEQUENCES'] = count
            printLog(log)
    
    # Print log
    log = OrderedDict()
    log['OUTPUT'] = ','.join([os.path.basename(f) for f in out_files])
    log['END'] = 'SplitSeq'
    printLog(log)
            
    return out_files

 
def downsizeSeqFile(seq_file, max_count, out_args=default_out_args):
    """
    Splits a FASTA/FASTQ file into segments with a limited number of records

    Arguments: 
    seq_file = filename of the FASTA file to split
    max_count = number of records in each output file
    out_args = common output argument dictionary from parseCommonArgs

    Returns: 
    a list of output file names
    """
    log = OrderedDict()
    log['START'] = 'SplitSeq'
    log['COMMAND'] = 'count'
    log['FILE'] = os.path.basename(seq_file) 
    log['MAX_COUNT'] = max_count
    printLog(log)
    
    # Open file handles
    in_type = getFileType(seq_file)
    seq_iter = readSeqFile(seq_file)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type
    # Determine total numbers of records
    rec_count = countSeqFile(seq_file)
    
    # Loop through iterator writing each record and opening new output handle as needed
    start_time = time()
    seq_count, part_num = 0, 1
    out_handle = getOutputHandle(seq_file, 'part%06i' % part_num, out_dir=out_args['out_dir'], 
                                 out_name=out_args['out_name'], out_type=out_args['out_type'])
    out_files = [out_handle.name]
    for seq in seq_iter:
        # Print progress for previous iteration
        printProgress(seq_count, rec_count, 0.05, start_time)
        
        # Update count
        seq_count += 1
        
        # Write records
        SeqIO.write(seq, out_handle, out_args['out_type'])
        # Break if total records reached to avoid extra empty file
        if seq_count == rec_count:
            break
        
        # Open new file if needed
        if seq_count % max_count == 0:
            out_handle.close()
            part_num += 1
            out_handle = getOutputHandle(seq_file, 'part%06i' % part_num, out_dir=out_args['out_dir'], 
                                         out_name=out_args['out_name'], out_type=out_args['out_type'])
            out_files.append(out_handle.name)
    
    # Print log
    printProgress(seq_count, rec_count, 0.05, start_time)
    log = OrderedDict()
    log['OUTPUT'] = ','.join([os.path.basename(f) for f in out_files])
    log['SEQUENCES'] = rec_count
    log['PARTS'] = len(out_files)
    log['END'] = 'SplitSeq'
    printLog(log)
    
    # Close file handles
    out_handle.close()

    return out_files


def groupSeqFile(seq_file, field, threshold=None, out_args=default_out_args):
    """
    Divides a sequence file into segments by description tags

    Arguments: 
    seq_file = filename of the sequence file to split
    field = The annotation field to split seq_file by
    threshold = The numerical threshold for group sequences by;
                if None treat field as textual
    out_args = common output argument dictionary from parseCommonArgs

    Returns: 
    a tuple of output file names
    """
    log = OrderedDict()
    log['START'] = 'SplitSeq'
    log['COMMAND'] = 'group'
    log['FILE'] = os.path.basename(seq_file) 
    log['FIELD'] = field
    log['THRESHOLD'] = threshold
    printLog(log)
    
    # Open file handles
    in_type = getFileType(seq_file)
    seq_iter = readSeqFile(seq_file)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type

    # Determine total numbers of records
    rec_count = countSeqFile(seq_file)

    # Process sequences
    start_time = time()
    seq_count = 0
    if threshold is None:
        # Sort records into files based on textual field
        # Create set of unique field tags
        temp_iter = readSeqFile(seq_file)
        tag_list = getAnnotationValues(temp_iter, field, unique=True, delimiter=out_args['delimiter'])
        # Create output handles
        handles_dict = {tag:getOutputHandle(seq_file, 
                                            tag, 
                                            out_dir=out_args['out_dir'], 
                                            out_name=out_args['out_name'], 
                                            out_type=out_args['out_type'])
                        for tag in tag_list}
        # Iterate over sequences
        for seq in seq_iter:
            printProgress(seq_count, rec_count, 0.05, start_time)
            seq_count += 1
            # Write sequences
            tag = parseAnnotation(seq.description, delimiter=out_args['delimiter'])[field]                
            SeqIO.write(seq, handles_dict[tag], out_args['out_type'])
    else:
        # Sort records into files based on numeric threshold   
        threshold = float(threshold)
        # Create output handles
        handles_dict = {'under':getOutputHandle(seq_file, 
                                                'under-%.1g' % threshold, 
                                                out_dir=out_args['out_dir'], 
                                                out_name=out_args['out_name'], 
                                                out_type=out_args['out_type']),
                        'atleast':getOutputHandle(seq_file, 
                                                  'atleast-%.1g' % threshold, 
                                                  out_dir=out_args['out_dir'], 
                                                  out_name=out_args['out_name'], 
                                                  out_type=out_args['out_type'])}
        # Iterate over sequences
        for seq in seq_iter:
            printProgress(seq_count, rec_count, 0.05, start_time)
            seq_count += 1
            # Write sequences
            tag = parseAnnotation(seq.description, delimiter=out_args['delimiter'])[field]
            tag = 'under' if float(tag) < threshold else 'atleast'
            SeqIO.write(seq, handles_dict[tag], out_args['out_type'])
    
    # Print log
    printProgress(seq_count, rec_count, 0.05, start_time)
    log = OrderedDict()
    log['OUTPUT'] = ','.join([os.path.basename(handles_dict[k].name) for k in handles_dict])
    log['SEQUENCES'] = rec_count
    log['PARTS'] = len(handles_dict)
    log['END'] = 'SplitSeq'
    printLog(log)
    
    # Close output file handles
    for k in handles_dict: handles_dict[k].close()

    return [handles_dict[k].name for k in handles_dict]


def sampleSeqFile(seq_file, max_count, field=None, values=None, out_args=default_out_args):
    """
    Samples from a sequence file

    Arguments: 
    seq_file = filename of the sequence file to sample from
    max_count = a list of the maximum number of sequences to sample
    field = the annotation field to check for required values
    values = a list of annotation values that a sample must contain one of
    out_args = common output argument dictionary from parseCommonArgs
              
    Returns: 
    the output file name
    """
    log = OrderedDict()
    log['START'] = 'SplitSeq'
    log['COMMAND'] = 'sample'
    log['FILE'] = os.path.basename(seq_file)
    log['MAX_COUNTS'] = ','.join([str(x) for x in max_count])
    log['FIELD'] = field
    log['VALUES'] = ','.join(values) if values else None
    printLog(log)
    
    # Read input files and open output files
    in_type = getFileType(seq_file)
    seq_dict = readSeqFile(seq_file, index=True)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type
    
    # Generate subset of records
    if field is not None and values is not None:
        key_list = subsetSeqIndex(seq_dict, field, values, delimiter=out_args['delimiter'])
    else:
        key_list = [k for k in seq_dict]
    # Determine total numbers of sampling records
    rec_count = len(key_list)

    # Generate sample set for each value in max_count
    out_files = []
    for i, c in enumerate(max_count):
        # Sample from records
        r = sample(range(rec_count), c) if c < rec_count else range(rec_count)
        sample_count = len(r)
        sample_keys = (key_list[x] for x in r)
        
        # Write sampled sequences to files
        with getOutputHandle(seq_file, 
                             'sample%i-n=%i' % (i + 1, sample_count), 
                             out_dir=out_args['out_dir'], 
                             out_name=out_args['out_name'], 
                             out_type=out_args['out_type']) as out_handle:
            for k in sample_keys:
                SeqIO.write(seq_dict[k], out_handle, out_args['out_type'])
            out_files.append(out_handle.name)
    
        # Print log for iteration
        log = OrderedDict()
        log['MAX_COUNT'] = c
        log['SAMPLED'] = sample_count
        printLog(log)
    
    # Print log
    log = OrderedDict()
    log['OUTPUT'] = ','.join([os.path.basename(f) for f in out_files])
    log['END'] = 'SplitSeq'
    printLog(log)
        
    return out_files


def samplePairSeqFile(seq_file_1, seq_file_2, max_count, field=None, values=None, 
                      coord_type=default_coord_type, out_args=default_out_args):
    """
    Samples from a sequence file

    Arguments: 
    seq_file_1 = filename of the first paired-end sequence file
    seq_file_2 = filename of the second paired-end sequence file
    max_count = a list of the maximum number of sequences to sample
    field = the annotation field to check for required values
    values = a list of annotation values that a sample must contain one of
    coord_type = the sequence header format
    out_args = common output argument dictionary from parseCommonArgs
              
    Returns: 
    a list of [seq_file_1, seq_file_2] output file names
    """
    log = OrderedDict()
    log['START']= 'SplitSeq'
    log['COMMAND'] = 'samplepair'
    log['FILE1'] = os.path.basename(seq_file_1)
    log['FILE2'] = os.path.basename(seq_file_2)
    log['MAX_COUNTS'] = ','.join([str(x) for x in max_count])
    log['FIELD'] = field
    log['VALUES'] = ','.join(values) if values else None
    printLog(log)
    
    # Read input files
    in_type_1 = getFileType(seq_file_1)
    seq_dict_1 = readSeqFile(seq_file_1, index=True)
    in_type_2 = getFileType(seq_file_2)
    seq_dict_2 = readSeqFile(seq_file_2, index=True)

    # Define output type
    if out_args['out_type'] is None:
        out_type_1 = in_type_1
        out_type_2 = in_type_2
    else: 
        out_type_1 = out_type_2 = out_args['out_type']

    # Define output name
    if out_args['out_name'] is None:
        out_name_1 = out_name_2 = None
    else: 
        out_name_1 = '%s-1' % out_args['out_name']
        out_name_2 = '%s-2' % out_args['out_name']

    # Find matching sequences
    index_dict = indexSeqPairs(seq_dict_1, seq_dict_2, coord_type, out_args['delimiter'])
    
    # Subset pair keys to those meeting field/value criteria
    if field is not None and values is not None:
        key_list_1 = subsetSeqIndex(seq_dict_1, field, values, delimiter=out_args['delimiter'])
        key_list_2 = subsetSeqIndex(seq_dict_2, field, values, delimiter=out_args['delimiter'])
        key_list = [k for k, (a, b) in index_dict.iteritems() \
                       if a in key_list_1 and b in key_list_2]
    else:
        key_list = index_dict.keys()
    # Determine total numbers of sampling pairs
    pair_count = len(key_list)

    # Generate sample set for each value in max_count
    out_files = []
    for i, c in enumerate(max_count):
        # Sample from paired set
        r = sample(range(pair_count), c) if c < pair_count else range(pair_count)
        sample_count = len(r)
        sample_keys = (key_list[x] for x in r)
        
        # Open file handles
        out_handle_1 = getOutputHandle(seq_file_1, 
                                       'sample%i-n=%i' % (i + 1, sample_count), 
                                       out_dir=out_args['out_dir'], 
                                       out_name=out_name_1, 
                                       out_type=out_type_1)
        out_handle_2 = getOutputHandle(seq_file_2, 
                                       'sample%i-n=%i' % (i + 1, sample_count), 
                                       out_dir=out_args['out_dir'], 
                                       out_name=out_name_2, 
                                       out_type=out_type_2)

        for k in sample_keys:
            key_1, key_2 = index_dict[k]
            SeqIO.write(seq_dict_1[key_1], out_handle_1, out_type_1)
            SeqIO.write(seq_dict_2[key_2], out_handle_2, out_type_2)
            out_files.append((out_handle_1.name, out_handle_2.name))
        
        # Print log for iteration
        log = OrderedDict()
        log['MAX_COUNT'] = c
        log['SAMPLED'] = sample_count
        printLog(log)
        
        # Close file handles
        out_handle_1.close()
        out_handle_2.close()
        
    # Print log
    log = OrderedDict()
    log['OUTPUT'] = ','.join([os.path.basename(f) for f in out_files])
    log['END'] = 'SplitSeq'
    printLog(log)
    
    return out_files


def sortSeqFile(seq_file, field, numeric=False, max_count=None, out_args=default_out_args):
    """
    Sorts a sequence file by annotation fields

    Arguments: 
    seq_file = filename of the sequence file to split
    field = position of field in sequence description to split by
    numeric = if True sort field numerically;
              if False sort field alphabetically
    max_count = maximum number of records in each output file
                if None do not create multiple files
    out_args = common output argument dictionary from parseCommonArgs
    
    Returns: 
    a list of output file names
    """
    log = OrderedDict()
    log['START'] = 'SplitSeq'
    log['COMMAND'] = 'sort'
    log['FILE'] = os.path.basename(seq_file)
    log['FIELD'] = field
    log['NUMERIC'] = numeric
    log['MAX_COUNT'] = max_count
    printLog(log)
    
    # Open file handles
    in_type = getFileType(seq_file)
    seq_dict = readSeqFile(seq_file, index=True)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type
    
    # Get annotations and sort seq_dict by annotation values
    tag_dict = {k:parseAnnotation(seq_dict[k].description, delimiter=out_args['delimiter'])[field]
                for k in seq_dict}
    if numeric:  tag_dict = {k:float(v or 0) for k, v in tag_dict.iteritems()}
    sorted_keys = sorted(tag_dict, key=tag_dict.get)
                
    # Determine total numbers of records
    rec_count = len(seq_dict)
    if max_count >= rec_count:  max_count = None

    # Open initial output file handles
    file_count = 1
    if max_count is None:  out_label = 'sorted'
    else:  out_label = 'sorted-part%06i' % file_count
    out_handle = getOutputHandle(seq_file, 
                                 out_label, 
                                 out_dir=out_args['out_dir'], 
                                 out_name=out_args['out_name'], 
                                 out_type=out_args['out_type'])
    out_files = [out_handle.name] 

    # Loop through sorted sequence dictionary keys
    start_time = time()
    last_tag = None
    saved_keys = []
    seq_count = chunk_count = 0
    for key in sorted_keys:
        # Print progress for previous iteration and update count
        printProgress(seq_count, rec_count, 0.05, start_time)
        seq_count += 1

        # Write saved group of sequences when tag changes
        if last_tag is not None and tag_dict[key] != last_tag:
            # Open new output file if needed
            if max_count is not None and chunk_count + len(saved_keys) > max_count:
                # Update partition counts
                file_count += 1
                chunk_count = 0
                # Open new file handle
                out_handle.close()
                out_handle = getOutputHandle(seq_file, 
                                             'sorted-part%06i' % file_count,
                                             out_dir=out_args['out_dir'], 
                                             out_name=out_args['out_name'], 
                                             out_type=out_args['out_type'])
                # Append output file name to out_files
                out_files.append(out_handle.name)
                
            # Write saved sequences
            for k in saved_keys:
                chunk_count += 1
                SeqIO.write(seq_dict[k], out_handle, out_args['out_type'])
            # Reset saved keys to current key only
            saved_keys = [key]
        else:
            # Update list of saved keys if tag is unchanged
            saved_keys.append(key)
            
        # Check if total records reached, write all saved keys, and exit loop
        if seq_count == rec_count:
            for k in saved_keys:
                chunk_count += 1
                SeqIO.write(seq_dict[k], out_handle, out_args['out_type'])
            out_handle.close()
            break

        # Update tag tracker
        last_tag = tag_dict[key]
        
    # Print log
    printProgress(seq_count, rec_count, 0.05, start_time)
    log = OrderedDict()
    log['OUTPUT'] = ','.join([os.path.basename(f) for f in out_files])
    log['SEQUENCES'] = seq_count
    log['PARTS'] = len(out_files)
    log['END'] = 'SplitSeq'
    printLog(log)
    
    # Close file handles
    out_handle.close()
    
    return out_files


def getArgParser():
    """
    Defines the ArgumentParser

    Arguments: 
    None
                      
    Returns: 
    an ArgumentParser object
    """
    # Define ArgumentParser
    parser = ArgumentParser(description=__doc__, version='%(prog)s:' + ' v%s-%s' %(__version__, __date__), 
                            formatter_class=ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='command', help='Parsing mode')
    
    # Subparser for file conversion
    parser_convert = subparsers.add_parser('convert', 
                                           parents=[getCommonArgParser(seq_out=False, annotation=False, log=False)],
                                           formatter_class=ArgumentDefaultsHelpFormatter,
                                           help='Converts sequence files')
    parser_convert.add_argument('--format', nargs='+', action='store', dest='out_format', 
                                required=True, choices=['fasta', 'fastq', 'embl', 'gb'],
                                help='Format(s) to convert sequence files to')
    parser_convert.set_defaults(func=convertSeqFile)

    # Subparser to downsize files to a maximum count
    parser_downsize = subparsers.add_parser('count', parents=[getCommonArgParser(annotation=False, log=False)],
                                            formatter_class=ArgumentDefaultsHelpFormatter,
                                            help='Splits sequences files by number of records')
    parser_downsize.add_argument('-n', action='store', dest='max_count', type=int, required=True,
                                 help='Maximum number of sequences in each new file')
    parser_downsize.set_defaults(func=downsizeSeqFile)
    
    # Subparser to partition files by annotation
    parser_group = subparsers.add_parser('group', parents=[getCommonArgParser(log=False)],
                                         formatter_class=ArgumentDefaultsHelpFormatter,
                                         help='Splits sequences files by annotation')
    parser_group.add_argument('-f', action='store', dest='field', type=str, required=True,
                              help='Annotation field to split sequence files by')
    parser_group.add_argument('--num', action='store', dest='threshold', type=float, default=None, 
                              help='Specify to define the split field as numeric and group \
                                    sequences by value')
    parser_group.set_defaults(func=groupSeqFile)

    # Subparser to randomly sample from unpaired files
    parser_sample = subparsers.add_parser('sample', parents=[getCommonArgParser(log=False)],
                                          formatter_class=ArgumentDefaultsHelpFormatter,
                                          help='Randomly samples from unpaired sequences files')
    parser_sample.add_argument('-n', nargs='+', action='store', dest='max_count', type=int, required=True, 
                               help='Maximum number of sequences to sample from each file')
    parser_sample.add_argument('-f', action='store', dest='field', type=str,
                               default=None, help='The annotation field for sampling criteria')
    parser_sample.add_argument('-u', nargs='+', action='store', dest='values', type=str, default=None, 
                               help='A list of annotation values that sequences must contain one of; \
                                     requires the -f argument')
    parser_sample.set_defaults(func=sampleSeqFile)
    
    # Subparser to randomly sample from paired files
    parser_samplepair = subparsers.add_parser('samplepair', parents=[getCommonArgParser(paired=True, log=False)],
                                          formatter_class=ArgumentDefaultsHelpFormatter,
                                          help='Randomly samples from paired-end sequences files')
    parser_samplepair.add_argument('-n', nargs='+', action='store', dest='max_count', type=int, 
                                   required=True, 
                                   help='A list of the number of sequences to sample from each file')
    parser_samplepair.add_argument('-f', action='store', dest='field', type=str,
                                   default=None, help='The annotation field for sampling criteria')
    parser_samplepair.add_argument('-u', nargs='+', action='store', dest='values', type=str, default=None, 
                                   help='A list of annotation values that both paired sequences must \
                                         contain one of; requires the -f argument')
    parser_samplepair.add_argument('--coord', action='store', dest='coord_type', 
                                   choices=default_coord_choices, default=default_coord_type,
                                   help='The format of the sequence identifier which defines shared \
                                         coordinate information across paired ends')
    parser_samplepair.set_defaults(func=samplePairSeqFile)
    
    # Subparser to sort files
    parser_sort = subparsers.add_parser('sort', parents=[getCommonArgParser(log=False)],
                                        formatter_class=ArgumentDefaultsHelpFormatter,
                                        help='Sorts sequences files by annotation')
    parser_sort.add_argument('-f', action='store', dest='field', type=str, required=True,
                             help='The annotation field to sort sequences by')
    parser_sort.add_argument('-n', action='store', dest='max_count', type=int,
                             default=None, help='Maximum number of sequences in each new file')
    parser_sort.add_argument('--num', action='store_true', dest='numeric',
                             help='Specify to define the sort field as numeric rather than textual')
    parser_sort.set_defaults(func=sortSeqFile)
    
    return parser


if __name__ == '__main__':
    """
    Parses command line arguments and calls main function
    """
    # Parse arguments
    parser = getArgParser()
    args = parser.parse_args()
    args_dict = parseCommonArgs(args)
    # Convert case of fields
    if 'field' in args_dict and args_dict['field']:  
        args_dict['field'] = args_dict['field'].upper()

    # Check if a valid option was specific for sample mode
    if (args.command == 'sample' or args.command == 'samplepair') and \
       (args.values and not args.field):
            parser.error('Samplings modes requires -f to be specified with -u')
    
    # Call appropriate function for each sample file
    del args_dict['command']
    del args_dict['func']
    if 'seq_files' in args_dict:
        del args_dict['seq_files']
        for f in args.__dict__['seq_files']:
            args_dict['seq_file'] = f
            args.func(**args_dict)
    elif 'seq_files_1' in args_dict and 'seq_files_2' in args_dict:
        del args_dict['seq_files_1']
        del args_dict['seq_files_2']
        for file_1, file_2 in zip(args.__dict__['seq_files_1'], args.__dict__['seq_files_2']):
            args_dict['seq_file_1'] = file_1
            args_dict['seq_file_2'] = file_2
            args.func(**args_dict)
        
        # Profiling
        #import cProfile, pstats
        #cProfile.run('args.func(**args_dict)', 'profile.prof')
        #p = pstats.Stats('profile.prof')
        #p.strip_dirs().sort_stats('time').print_stats() 