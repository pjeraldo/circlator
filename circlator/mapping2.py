import os
import pysam
import pyfastaq
from circlator import common, external_progs

class Error (Exception): pass


index_extensions = [
        'mmi'
]

def minimap2(
      ref,
      reads,
      outfile,
      threads=1,
      data_type = 'pacbio-raw',
      verbose=False,
      index=None
    ):

    samtools = external_progs.make_and_check_prog('samtools', verbose=verbose)
    minimap2 = external_progs.make_and_check_prog('minimap2', verbose=verbose)
    unsorted_bam = outfile + '.tmp.unsorted.bam'

    if startswith(data_type) == 'pacbio':
        map_reads_type= 'map-pb'
    else:
        map_reads_type= 'map-ont'

    cmd = ' '.join([
        minimap2.exe(),
        '-a',
        '-x', map_reads_type,
        '--MD',
        '--secondary', 'no',
        '-t', str(threads),
        ref,
        reads,
        '|',
        samtools.exe(), 'view',
        '-F', '0x0900', #no secondary or supplementary alignments
        '-T', ref,
        '-o', unsorted_bam,
        '-',
    ])

    common.syscall(cmd, verbose=verbose)
    threads = min(4, threads)
    thread_mem = int(500 / threads)

    cmd = ' '.join([
        samtools.exe(), 'sort',
        '-@', str(threads),
        '-m', str(thread_mem) + 'M',
        unsorted_bam,
        '-o', outfile
    ])

    common.syscall(cmd, verbose=verbose)
    os.unlink(unsorted_bam)

    cmd = samtools.exe() + ' index ' + outfile
    common.syscall(cmd, verbose=verbose)


def aligned_read_to_read(read, revcomp=True, qual=None, ignore_quality=False):
    '''Returns Fasta or Fastq sequence from pysam aligned read'''
    if read.qual is None or ignore_quality:
        if qual is None or ignore_quality:
            seq = pyfastaq.sequences.Fasta(read.qname, common.decode(read.seq))
        else:
            seq = pyfastaq.sequences.Fastq(read.qname, common.decode(read.seq), qual * read.query_length)
    else:
        if qual is None:
            seq = pyfastaq.sequences.Fastq(read.qname, common.decode(read.seq), common.decode(read.qual))
        else:
            seq = pyfastaq.sequences.Fastq(read.qname, common.decode(read.seq), qual * read.query_length)

    if read.is_reverse and revcomp:
        seq.revcomp()

    return seq
