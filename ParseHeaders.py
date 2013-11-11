#!/usr/bin/env python
"""
Parses pRESTO annotations in FASTA/FASTQ sequence headers
"""

__author__    = 'Jason Anthony Vander Heiden'
__copyright__ = 'Copyright 2013 Kleinstein Lab, Yale University. All rights reserved.'
__license__   = 'Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported'
__version__   = '0.4.1'
__date__      = '2013.11.10'

# Imports
import csv, os, re, sys
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from collections import OrderedDict
from itertools import izip
from time import time
from Bio import SeqIO

# IgCore imports
sys.path.append(os.path.dirname(os.path.realpath(__file__)))
from IgCore import default_action_choices, default_delimiter, default_out_args
from IgCore import collapseAnnotation, flattenAnnotation, mergeAnnotation
from IgCore import parseAnnotation, renameAnnotation
from IgCore import getCommonArgParser, parseCommonArgs
from IgCore import getOutputHandle, printLog, printProgress
from IgCore import countSeqFile, readSeqFile, getFileType

# Defaults
default_separator = ','


def addHeader(header, fields, values, delimiter=default_delimiter):
    """
    Adds fields and values to a sequence header

    Arguments: 
    header = an annotation dictionary returned by parseAnnotation
    fields = the list of fields to add or append to
    values = the list of annotation values to add for each field
    delimiter = a tuple of delimiters for (fields, values, value lists)
                    
    Returns: 
    the modified header dictionary
    """
    for f, v in izip(fields, values):
        header = mergeAnnotation(header, {f:v}, delimiter=delimiter)
        
    return header


def collapseHeader(header, fields, actions, delimiter=default_delimiter):
    """
    Collapses a sequence header

    Arguments: 
    header = an annotation dictionary returned by parseAnnotation
    fields = the list of fields to collapse
    actions = the list of collapse action take;
              one of (max, min, sum, first, last, set) for each field
    delimiter = a tuple of delimiters for (fields, values, value lists)
                    
    Returns: 
    the output file name
    """
    for f, a in izip(fields, actions):
        header = collapseAnnotation(header, a, f, delimiter=delimiter)
        
    return header


def deleteHeader(header, fields, delimiter=default_delimiter):
    """
    Deletes fields from a sequence header

    Arguments: 
    header = an annotation dictionary returned by parseAnnotation
    fields = the list of fields to delete
    delimiter = a tuple of delimiters for (fields, values, value lists)
                        
    Returns: 
    the modified header dictionary
    """
    for f in fields:  del header[f]

    return header


def expandHeader(header, fields, separator=default_separator, 
                 delimiter=default_delimiter):
    """
    Splits and annotation value into separate fields in a sequence header

    Arguments: 
    header = an annotation dictionary returned by parseAnnotation
    fields = the field to split
    separator = the delimiter to split the values by
    delimiter = a tuple of delimiters for (fields, values, value lists)
                        
    Returns: 
    the modified header dictionary
    """
    for f in fields:
        values = header[f].split(separator)
        names = [f + str(i + 1) for i in range(len(values))]
        ann = OrderedDict([(n, v) for n, v in izip(names, values)])
        header = mergeAnnotation(header, ann, delimiter=delimiter)
        del header[f]
    
    return header


def renameHeader(header, fields, names, delimiter=default_delimiter):
    """
    Renames fields in a sequence header

    Arguments: 
    header = an annotation dictionary returned by parseAnnotation
    fields = a list of the current field names
    names = a list of the new field names
    delimiter = a tuple of delimiters for (fields, values, value lists)
                            
    Returns: 
    the modified header dictionary
    """
    for f, n in izip(fields, names):
        header = renameAnnotation(header, f, n, delimiter=delimiter)
        
    return header


def modifyHeaders(seq_file, modify_func, modify_args, out_args=default_out_args):
    """
    Modifies sequence headers

    Arguments: 
    seq_file = the sequence file name
    modify_func = the function defining the modification operation
    modify_args = a dictionary of arguments to pass to modify_func
    out_args = common output argument dictionary from parseCommonArgs
                    
    Returns: 
    the output file name
    """
    # Define subcommand label dictionary
    cmd_dict = {addHeader:'add', collapseHeader:'collapse', deleteHeader:'delete', 
                expandHeader:'expand', renameHeader:'rename'}
    
    # Print parameter info
    log = OrderedDict()
    log['START'] = 'ParseHeaders'
    log['COMMAND'] = cmd_dict.get(modify_func, modify_func.__name__)
    log['FILE'] = os.path.basename(seq_file)
    for k in sorted(modify_args):  
        v = modify_args[k]
        log[k.upper()] = ','.join(v) if isinstance(v, list) else v
    printLog(log)
    
    # Open file handles
    in_type = getFileType(seq_file)
    seq_iter = readSeqFile(seq_file)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type
    out_handle = getOutputHandle(seq_file, 'reheader', out_dir=out_args['out_dir'],
                                 out_name=out_args['out_name'], out_type=out_args['out_type'])

    # Count records
    result_count = countSeqFile(seq_file)
    
    # Iterate over sequences
    start_time = time()
    seq_count = 0
    for seq in seq_iter:
        # Print progress for previous iteration
        printProgress(seq_count, result_count, 0.05, start_time)
        
        #Update counts
        seq_count += 1
        
        # Modify header
        header = parseAnnotation(seq.description, delimiter=out_args['delimiter'])
        header = modify_func(header, delimiter=out_args['delimiter'], **modify_args)
        
        # Write new sequence
        seq.id = seq.name = flattenAnnotation(header, delimiter=out_args['delimiter'])
        seq.description = ''
        SeqIO.write(seq, out_handle, out_args['out_type'])
        
    # print counts
    printProgress(seq_count, result_count, 0.05, start_time)    
    log = OrderedDict()
    log['OUTPUT'] = os.path.basename(out_handle.name)
    log['SEQUENCES'] = seq_count
    log['END'] = 'ParseHeaders'               
    printLog(log)

    # Close file handles
    out_handle.close()
 
    return out_handle.name


def tableHeaders(seq_file, fields, out_args=default_out_args):
    """
    Builds a table of sequence header annotations

    Arguments: 
    seq_file = the sequence file name
    fields = the list of fields to output
    out_args = common output argument dictionary from parseCommonArgs
                    
    Returns: 
    the output table file name
    """
    log = OrderedDict()
    log['START'] = 'ParseHeaders'
    log['COMMAND'] = 'table'
    log['FILE'] = os.path.basename(seq_file)
    printLog(log)
    
    # Open file handles
    seq_iter = readSeqFile(seq_file)
    out_handle = getOutputHandle(seq_file, out_label='headers', out_dir=out_args['out_dir'], 
                                 out_name=out_args['out_name'], out_type='tab')
    # Count records
    result_count = countSeqFile(seq_file)
    
    # Open csv writer and write header
    out_writer = csv.DictWriter(out_handle, extrasaction='ignore', restval='', 
                                delimiter='\t', fieldnames=fields)
    out_writer.writeheader()
    
    # Iterate over sequences
    start_time = time()
    seq_count = pass_count = fail_count = 0
    for seq in seq_iter:
        # Print progress for previous iteration
        printProgress(seq_count, result_count, 0.05, start_time)
        
        # Get annotations
        seq_count += 1
        ann = parseAnnotation(seq.description, fields, delimiter=out_args['delimiter'])

        # Write records
        if ann:
            pass_count += 1
            out_writer.writerow(ann)
        else:
            fail_count += 1
        
    # Print counts
    printProgress(seq_count, result_count, 0.05, start_time)
    log = OrderedDict()
    log['OUTPUT'] = os.path.basename(out_handle.name)
    log['SEQUENCES'] = seq_count
    log['PASS'] = pass_count
    log['FAIL'] = fail_count
    log['END'] = 'ParseHeaders'
    printLog(log)

    # Close file handles
    out_handle.close()
 
    return out_handle.name


def convertHeaders(seq_file, out_args=default_out_args):
    """
    Builds a table of sequence header annotations

    Arguments: 
    seq_file = the sequence file name
    out_args = common output argument dictionary from parseCommonArgs
                    
    Returns: 
    the output sequence file name
    """
    log = OrderedDict()
    log['START'] = 'ParseHeaders'
    log['COMMAND'] = 'convert'
    log['FILE'] = os.path.basename(seq_file)
    printLog(log)
    
    # Open input file
    in_type = getFileType(seq_file)
    seq_iter = readSeqFile(seq_file)
    if out_args['out_type'] is None:  out_args['out_type'] = in_type
    
    # Count records
    result_count = countSeqFile(seq_file)

    # Define replacement regular expressions
    d = re.escape(out_args['delimiter'][0])
    end_re = re.compile('(\s+%s+\s+)|(\s+%s+)|(%s+\s+)' % (d, d, d))
    inner_re = re.compile('%s+' % d)
    space_re = re.compile(r'\s+')

    # Open output file handles
    pass_handle = getOutputHandle(seq_file, 
                                  'reheader-pass', 
                                  out_dir=out_args['out_dir'],
                                  out_name=out_args['out_name'], 
                                  out_type=out_args['out_type'])
    if not out_args['clean']:
        fail_handle = getOutputHandle(seq_file, 
                                      'reheader-fail', 
                                      out_dir=out_args['out_dir'],
                                      out_name=out_args['out_name'], 
                                      out_type=out_args['out_type'])
    else:
        fail_handle = None
        
    # Iterate over sequences
    start_time = time()
    seq_count = pass_count = fail_count = 0
    for seq in seq_iter:
        # Print progress for previous iteration and update count
        printProgress(seq_count, result_count, 0.05, start_time)
        seq_count += 1
        
        try:
            # Check if header is already valid
            parseAnnotation(seq.description, delimiter=out_args['delimiter'])
        except:
            # Attempt to convert header
            header = re.sub(end_re, ' ', seq.description)
            header = re.sub(inner_re, '_', header)
            header = re.sub(space_re, ' ', header)
            try:
                # Check if modified header is valid
                parseAnnotation(header, delimiter=out_args['delimiter'])
            except:
                # Assign header to None if header cannot be converted
                header = None
        else:
            # Assign header to seq.description if already valid
            header = seq.description

        if header is not None:
            # Write successfully converted sequences
            pass_count += 1
            seq.id = seq.name = header
            seq.description = ''
            SeqIO.write(seq, pass_handle, out_args['out_type'])
        else:
            fail_count += 1
            if fail_handle is not None:
                # Write successfully unconverted sequences
                SeqIO.write(seq, fail_handle, out_args['out_type'])
        
    # Print counts
    printProgress(seq_count, result_count, 0.05, start_time)
    log = OrderedDict()
    log['OUTPUT'] = os.path.basename(pass_handle.name)
    log['SEQUENCES'] = seq_count
    log['PASS'] = pass_count
    log['FAIL'] = fail_count
    log['END'] = 'ParseHeaders'
    printLog(log)

    # Close file handles
    pass_handle.close()
    if fail_handle is not None:  fail_handle.close()
    
    return pass_handle.name


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
    subparsers = parser.add_subparsers(dest='command')
    
    # Subparser to add header fields
    parser_add = subparsers.add_parser('add', parents=[getCommonArgParser(log=False)],
                                       formatter_class=ArgumentDefaultsHelpFormatter,
                                       help='Adds field/value pairs to header annotations')    
    parser_add.add_argument('-f', nargs='+', action='store', dest='fields', required=True,
                            help='List of fields to add')
    parser_add.add_argument('-u', nargs='+', action='store', dest='values', required=True,
                            help='List of values to add for each field')
    parser_add.set_defaults(func=modifyHeaders)
    parser_add.set_defaults(modify_func=addHeader)

    # Subparser to collapse header fields
    parser_collapse = subparsers.add_parser('collapse', parents=[getCommonArgParser(log=False)],
                                            formatter_class=ArgumentDefaultsHelpFormatter,
                                            help='Collapses header annotations with multiple entries')    
    parser_collapse.add_argument('-f', nargs='+', action='store', dest='fields', required=True,
                                 help='List of fields to collapse')
    parser_collapse.add_argument('--act', nargs='+', action='store', dest='actions', required=True,
                                 choices=default_action_choices,
                                 help='List of actions to take for each field')
    parser_collapse.set_defaults(func=modifyHeaders)
    parser_collapse.set_defaults(modify_func=collapseHeader)

    # Subparser to delete header fields
    parser_delete = subparsers.add_parser('delete', parents=[getCommonArgParser(log=False)],
                                          formatter_class=ArgumentDefaultsHelpFormatter,
                                          help='Deletes fields from header annotations')    
    parser_delete.add_argument('-f', nargs='+', action='store', dest='fields', required=True,
                               help='List of fields to delete')
    parser_delete.set_defaults(func=modifyHeaders)
    parser_delete.set_defaults(modify_func=deleteHeader)

    # Subparser to expand header fields
    parser_expand = subparsers.add_parser('expand', parents=[getCommonArgParser(log=False)],
                                          formatter_class=ArgumentDefaultsHelpFormatter,
                                          help='Expands annotation fields with multiple values')    
    parser_expand.add_argument('-f', nargs='+', action='store', dest='fields', required=True,
                               help='List of fields to expand')
    parser_expand.add_argument('--sep', action='store', dest='separator', 
                               default=default_separator,
                               help='The character separating each value in the fields')
    parser_expand.set_defaults(func=modifyHeaders)
    parser_expand.set_defaults(modify_func=expandHeader)

    # Subparser to rename header fields
    parser_rename = subparsers.add_parser('rename', parents=[getCommonArgParser(log=False)],
                                          formatter_class=ArgumentDefaultsHelpFormatter,
                                          help='Renames headers annotation fields')    
    parser_rename.add_argument('-f', nargs='+', action='store', dest='fields', required=True,
                               help='List of fields to rename')
    parser_rename.add_argument('-k', nargs='+', action='store', dest='names', required=True,
                               help='List of new names for each field')
    parser_rename.set_defaults(func=modifyHeaders)
    parser_rename.set_defaults(modify_func=renameHeader)
            
    # Subparser to create a header table
    parser_table = subparsers.add_parser('table', parents=[getCommonArgParser(seq_out=False, log=False)],
                                         formatter_class=ArgumentDefaultsHelpFormatter,
                                         help='Writes sequence headers to a table')
    parser_table.add_argument('-f', nargs='+', action='store', dest='fields', required=True,
                              help='List of fields to collect')
    parser_table.set_defaults(func=tableHeaders)
    
    # Subparser to convert header to pRESTO format
    parser_convert = subparsers.add_parser('convert', parents=[getCommonArgParser(log=False)],
                                       formatter_class=ArgumentDefaultsHelpFormatter,
                                       help='Converts sequence descriptions to pRESTO format')   
    parser_convert.set_defaults(func=convertHeaders)
    
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
    if 'fields' in args_dict and args_dict['fields']:  
        args_dict['fields'] = map(str.upper, args_dict['fields'])
    # Built modify_args dictionary
    if args.func == modifyHeaders:
        modify_args = {}
        if 'fields' in args_dict:  
            modify_args['fields'] = args_dict.pop('fields')
        if 'actions' in args_dict:  
            modify_args['actions'] = map(str.lower, args_dict.pop('actions')) 
        if 'names' in args_dict:  
            modify_args['names'] = map(str.upper, args_dict.pop('names'))
        if 'values' in args_dict: 
            modify_args['values'] = args_dict.pop('values')
        if 'separator' in args_dict: 
            modify_args['separator'] = args_dict.pop('separator')
        args_dict['modify_args'] = modify_args
        
    # Check modify_args arguments
    if args.command == 'add' and len(modify_args['fields']) != len(modify_args['values']):
        parser.error('You must specify exactly one value (-x) per field (-f)')
    if args.command == 'collapse' and len(modify_args['fields']) != len(modify_args['actions']):
        parser.error('You must specify exactly one action (-a) per field (-f)')
    
    # Calls header processing function
    del args_dict['command']
    del args_dict['func']
    del args_dict['seq_files']
    for f in args.__dict__['seq_files']:
        args_dict['seq_file'] = f
        args.func(**args_dict)

        # Profiling
        #import cProfile, pstats
        #cProfile.run('parseLog(**args_dict)', 'profile.prof')
        #p = pstats.Stats('profile.prof')
        #p.strip_dirs().sort_stats('time').print_stats() 