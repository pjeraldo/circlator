import argparse
import sys
import circlator

def run():
    parser = argparse.ArgumentParser(
        description = 'Map reads using minimap2',
        usage = 'circlator mapreads [options] <reference.fasta> <reads.fasta> <out.bam>')
    parser.add_argument('--data_type', choices=circlator.common.allowed_data_types, help='String representing one of the 4 type of data analysed [%(default)s]', default='pacbio-raw')
    parser.add_argument('--threads', type=int, help='Number of threads [%(default)s]', default=1, metavar='INT')
    parser.add_argument('--verbose', action='store_true', help='Be verbose')
    parser.add_argument('ref', help='Name of input reference FASTA file', metavar='reference.fasta')
    parser.add_argument('reads', help='Name of corrected reads FASTA file', metavar='reads.fasta')
    parser.add_argument('bam', help='Name of output BAM file', metavar='out.bam')
    options = parser.parse_args()

    circlator.mapping2.minimap2(
      options.ref,
      options.reads,
      options.bam,
      threads=options.threads,
      data_type=options.data_type,
      verbose=options.verbose,
    )
