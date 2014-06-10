#!/usr/bin/env python
"""
Removes duplicate sequences from FASTA/FASTQ files
"""

__author__    = 'Jason Anthony Vander Heiden'
__copyright__ = 'Copyright 2013 Kleinstein Lab, Yale University. All rights reserved.'
__license__   = 'Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported'
__version__   = '0.4.4'
__date__      = '2014.6.10'

# Imports
import os, re, sys
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict
from itertools import chain, izip
from time import time
from Bio import SeqIO

# IgCore imports
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from IgCore import default_action_choices, default_delimiter, default_out_args
from IgCore import collapseAnnotation, flattenAnnotation 
from IgCore import mergeAnnotation, parseAnnotation
from IgCore import getCommonArgParser, parseCommonArgs
from IgCore import getOutputHandle, printLog, printProgress
from IgCore import getFileType, readSeqFile, testSeqEqual

# Default parameters
default_max_missing = 0


def findUID(uid, search_dict, score=False):
    """
    Checks if a unique identifier is already present in a unique dictionary

    Arguments: 
    uid = the unique identifier key to check
    search_dict = a dictionary to search for key matches in
    score = if True score sequence element of the uid against each sequence in search_list

    Returns: 
    uid of match if found; None otherwise
    """
    match = None
    # Check for exact matches
    if not score:
        match = uid if uid in search_dict else None
    # Check for ambiguous matches
    else:
        for key in search_dict:
            if uid[1:] == key[1:] and testSeqEqual(uid[0], key[0]):
                match = key 
                break
    
    # Return search boolean
    return match


def findUniqueSeq(uniq_dict, search_keys, seq_dict, max_missing=default_max_missing, 
                  uniq_fields=None, copy_fields=None, max_field=None, min_field=None, 
                  inner=False, delimiter=default_delimiter):
    """
    Finds unique sequences 

    Arguments: 
    uniq_dict = a dictionary of unique sequences generated by findUniqueSeq()
    search_keys = a list containing the subset of dictionary keys to be checked
    seq_dict = a SeqRecords dictionary generated by SeqIO.index()
    max_missing = the number of missing characters to allow in a unique sequences
    uniq_fields = a list of annotations that define a sequence as unique if they differ
    copy_fields = a list of annotations to copy into unique sequence annotations
    max_field = a numeric field whose maximum value determines the retained sequence
    min_field = a numeric field whose minimum value determines the retained sequence
    inner = if True exclude consecutive outer ambiguous characters from iterations and matching
    delimiter = description field delimiter
    
    Returns: 
    a tuple of (uniq_dict, search_keys, dup_keys) modified from passed values
    """
    # Define local variable
    ambig_re = re.compile(r'[\.\-N]')
    score = (max_missing > 0)
    dup_keys = []
    to_remove = []
    
    start_time = time()
    result_count = len(search_keys)
    print 'MISSING>  %i' % max_missing
    # Iterate over search keys and update uniq_dict and dup_keys
    for idx, key in enumerate(search_keys):
        # Print progress of previous iteration
        printProgress(idx, result_count, 0.05, start_time)
        
        # Define sequence to process
        seq = seq_dict[key]
        seq_str = str(seq.seq)
        if inner:  seq_str = seq_str.strip('.-N')
        
        # Skip processing of ambiguous sequences over max_missing threshold 
        ambig_count = len(ambig_re.findall(seq_str))
        if ambig_count > max_missing:  continue
        
        # Parse annotation and define unique identifiers (uid)
        if uniq_fields is not None:
            ann = parseAnnotation(seq_dict[key].description, uniq_fields, delimiter=delimiter)
            uid = tuple(chain([seq_str], ann.values()))             
        else:
            uid = (seq_str, None)

        # Parse annotation and define copied identifiers (cid)        
        if copy_fields is not None:
            ann = parseAnnotation(seq.description, copy_fields, delimiter=delimiter)
            #print ann
            #cid = [[a] for a in ann.values()]
            cid = [[ann.get(k)] for k in copy_fields]
            #print cid
        else:
            cid = []

        # Store new unique sequences and process duplicates
        match = findUID(uid, uniq_dict, score)
        if match is None:
            uniq_dict[uid] = list(chain([seq, 1, ambig_count], cid))
        else:
            # Updated sequence, count, ambiguous character count, and count sets
            dup_key = key
            uniq_dict[match][1] += 1
            for x, c in enumerate(cid):
                uniq_dict[match][3 + x].extend(c)
            # Check whether to replace previous unique sequence with current sequence
            if ambig_count <= uniq_dict[match][2]:
                swap = False
                seq_last = uniq_dict[match][0]
                if max_field is not None:
                    swap = float(parseAnnotation(seq.description, delimiter=delimiter)[max_field]) > \
                           float(parseAnnotation(seq_last.description, delimiter=delimiter)[max_field])
                elif min_field is not None:
                    swap = float(parseAnnotation(seq.description, delimiter=delimiter)[min_field]) > \
                           float(parseAnnotation(seq_last.description, delimiter=delimiter)[min_field])
                # >>> QUALITY EVALUATION IS A BOTTLENECK
                else:
                    if hasattr(seq, 'letter_annotations') and 'phred_quality' in seq.letter_annotations:
                        q_this = float(sum(seq.letter_annotations['phred_quality'])) / len(seq)
                        q_last = float(sum(seq_last.letter_annotations['phred_quality'])) / len(seq_last)
                        swap = q_this > q_last
                # Replace old sequence if criteria passed
                if swap:
                    dup_key = seq_last.id
                    #uniq_dict[match] = [seq, uniq_dict[match][1], ambig_count]
                    uniq_dict[match][0] = seq
                    uniq_dict[match][2] = ambig_count
                    
            # Update duplicate list
            dup_keys.append(dup_key)

        # Mark seq for removal from later steps
        to_remove.append(idx)
        
    # Remove matched sequences from search_keys
    for j in reversed(to_remove):  del search_keys[j]

    # Update progress
    printProgress(result_count, result_count, 0.05, start_time)
        
    return (uniq_dict, search_keys, dup_keys)


def collapseSeq(seq_file, max_missing=default_max_missing, uniq_fields=None,
                copy_fields=None, copy_actions=None, max_field=None, min_field=None, 
                inner=False, out_args=default_out_args):
    """
    Removes duplicate sequences from a file

    Arguments: 
    seq_file = filename of the sequence file to sample from
    max_missing = number of ambiguous charactes to allow in a unique sequence
    uniq_fields = a list of annotations that define a sequence as unique if they differ
    copy_fields = a list of annotations to copy into unique sequence annotations
    copy_actions = the list of collapseAnnotation actions to take on copy_fields 
    max_field = a numeric field whose maximum value determines the retained sequence
    min_field = a numeric field whose minimum value determines the retained sequence
    inner = if True exclude consecutive outer ambiguous characters from iterations and matching
    out_args = common output argument dictionary from parseCommonArgs
              
    Returns: 
    the collapsed output file name
    """
    log = OrderedDict()
    log['START'] = 'CollapseSeq'
    log['FILE'] = os.path.basename(seq_file)
    log['MAX_MISSING'] = max_missing
    log['UNIQ_FIELDS'] = ','.join([str(x) for x in uniq_fields]) \
                         if uniq_fields is not None else None
    log['COPY_FIELDS'] = ','.join([str(x) for x in copy_fields]) \
                         if copy_fields is not None else None
    log['COPY_ACTIONS'] = ','.join([str(x) for x in copy_actions]) \
                          if copy_actions is not None else None
    log['MAX_FIELD'] = max_field
    log['MIN_FIELD'] = min_field
    log['INNER'] = inner
    printLog(log)
    
    # Read input file
    in_type = getFileType(seq_file)
    seq_dict = readSeqFile(seq_file, index=True)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type

    # Count total sequences
    rec_count = len(seq_dict)

    # Define log handle
    if out_args['log_file'] is None:  
        log_handle = None
    else:  
        log_handle = open(out_args['log_file'], 'w')

    # Find sequences with duplicates
    uniq_dict = {}
    # Added list typing for compatibility issue with Python 2.7.5 on OS X
    # TypeError: object of type 'dictionary-keyiterator' has no len()
    search_keys = list(seq_dict.keys())
    dup_keys = []
    for n in range(0, max_missing + 1):
        # Find unique sequences
        uniq_dict, search_keys, dup_list = findUniqueSeq(uniq_dict, search_keys, seq_dict, n, 
                                                         uniq_fields, copy_fields,
                                                         max_field, min_field, inner, 
                                                         out_args['delimiter'])
        # Update list of duplicates
        dup_keys.extend(dup_list)

        # Update log
        log = OrderedDict()
        log['ITERATION'] = n + 1
        log['MISSING'] = n 
        log['UNIQUE'] = len(uniq_dict) 
        log['DUPLICATE'] = len(dup_keys) 
        log['UNDETERMINED'] = len(search_keys)
        printLog(log, handle=log_handle)
                
        # Break if no keys to search remain
        if len(search_keys) == 0:
            break
    
    # Write unique sequences
    with getOutputHandle(seq_file, 'collapse-unique', out_dir=out_args['out_dir'], 
                         out_name=out_args['out_name'], out_type=out_args['out_type']) \
            as uniq_handle:
        for val in uniq_dict.itervalues():
            # Define output sequence
            out_seq = val[0]
            out_ann = parseAnnotation(out_seq.description, delimiter=out_args['delimiter'])
            out_app = OrderedDict()
            if copy_fields  is not None and copy_actions is not None:
                for f, a, s in izip(copy_fields, copy_actions, val[3:]):
                    out_app[f] = s
                    out_app = collapseAnnotation(out_app, a, f, delimiter=out_args['delimiter'])
                    out_ann.pop(f, None)
            out_app['DUPCOUNT'] = val[1]
            out_ann = mergeAnnotation(out_ann, out_app, delimiter=out_args['delimiter'])
            out_seq.id = out_seq.name = flattenAnnotation(out_ann, delimiter=out_args['delimiter'])
            out_seq.description = ''
            # Write unique sequence
            SeqIO.write(out_seq, uniq_handle, out_args['out_type'])
    
    if not out_args['clean']:
        # Write duplicate sequences 
        with getOutputHandle(seq_file, 'collapse-duplicate', out_dir=out_args['out_dir'], 
                             out_name=out_args['out_name'], out_type=out_args['out_type']) \
                as dup_handle:
            for k in dup_keys:
                SeqIO.write(seq_dict[k], dup_handle, out_args['out_type'])
        
        # Write sequence with high missing character counts
        with getOutputHandle(seq_file, 'collapse-undetermined', out_dir=out_args['out_dir'], 
                             out_name=out_args['out_name'], out_type=out_args['out_type']) \
                as missing_handle:
            for k in search_keys:
                SeqIO.write(seq_dict[k], missing_handle, out_args['out_type'])
    
    # Print log
    log = OrderedDict()
    log['OUTPUT'] = os.path.basename(uniq_handle.name)
    log['SEQUENCES'] = rec_count
    log['UNIQUE'] = len(uniq_dict)
    log['DUPLICATE'] = len(dup_keys)
    log['UNDETERMINED'] = len(search_keys)
    log['END'] = 'CollapseSeq'
    printLog(log)
        
    # Close file handles
    if log_handle is not None:  log_handle.close()
    
    return uniq_handle.name
    

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
                            parents=[getCommonArgParser()], 
                            formatter_class=ArgumentDefaultsHelpFormatter)

    parser.add_argument('-n', action='store', dest='max_missing', type=int, default=default_max_missing, 
                        help='Maximum number of missing nucleotides to consider for collapsing \
                              sequences; a sequence will be considered undetermined if it contains too \
                              many missing nucleotides')
    parser.add_argument('--uf', nargs='+', action='store', dest='uniq_fields', type=str, default=None, 
                        help='Specifies a set of annotation fields that must match for sequences \
                              to be considered duplicates')
    parser.add_argument('--cf', nargs='+', action='store', dest='copy_fields', type=str, default=None, 
                        help='Specifies a set of annotation fields to copy into the unique \
                              sequence output')
    parser.add_argument('--act', nargs='+', action='store', dest='copy_actions', default=None,
                        choices=default_action_choices,
                        help='List of actions to take for each copy field')
    parser.add_argument('--inner', action='store_true', dest='inner',
                        help='If specified exclude consecutive missing characters at either end of \
                              the sequence')
    arg_group = parser.add_mutually_exclusive_group()
    arg_group.add_argument('--maxf', action='store', dest='max_field', type=str, default=None,
                           help='Specify the field whose maximum value determines the retained sequence; \
                                 mutually exclusive with --minf')
    arg_group.add_argument('--minf', action='store', dest='min_field', type=str, default=None,
                           help='Specify the field whose minimum value determines the retained sequence; \
                                 mutually exclusive with --minf')    
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
    if 'uniq_fields' in args_dict and args_dict['uniq_fields']:  
        args_dict['uniq_fields'] = map(str.upper, args_dict['uniq_fields']) 
    if 'copy_fields' in args_dict and args_dict['copy_fields']:
        args_dict['copy_fields'] = map(str.upper, args_dict['copy_fields'])
    if 'copy_actions' in args_dict and args_dict['copy_actions']:
        args_dict['copy_actions'] = map(str.lower, args_dict['copy_actions'])
    if 'max_field' in args_dict and args_dict['max_field']:  
        args_dict['max_field'] = args_dict['max_field'].upper() 
    if 'min_field' in args_dict and args_dict['min_field']:  
        args_dict['min_field'] = args_dict['min_field'].upper()
    
    # Check copy field and action arguments
    if bool(args_dict['copy_fields']) ^ bool(args_dict['copy_actions']) or \
       len((args_dict['copy_fields'] or '')) != len((args_dict['copy_actions'] or '')):
            parser.error('You must specify exactly one copy action (--act) per copy field (--cf)')
    
    # Call appropriate function for each sample file
    del args_dict['seq_files']
    for f in args.__dict__['seq_files']:
        args_dict['seq_file'] = f
        collapseSeq(**args_dict)
