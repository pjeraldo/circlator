import os
import tempfile
import sys
import shutil
import pyfastaq
from circlator import common, external_progs

class Error (Exception): pass

class Assembler:
    def __init__(self,
      reads,
      outdir,
      threads=1,
      spades_kmers=None,
      careful=True,
      only_assembler=True,
      verbose=False,
      spades_use_first_success=False,
      assembler='racon',
      genomeSize=100000, # only matters for Canu if correcting reads (which we're not)
      racon_rounds=2,
      data_type='pacbio-raw',
    ):
        self.outdir = os.path.abspath(outdir)
        self.reads = os.path.abspath(reads)
        if not os.path.exists(self.reads):
            raise Error('Reads file not found:' + self.reads)

        self.verbose = verbose
        self.samtools = external_progs.make_and_check_prog('samtools', verbose=self.verbose)
        self.threads = threads
        self.assembler = assembler

        if self.assembler == 'spades':
            self.spades = external_progs.make_and_check_prog('spades', verbose=self.verbose, required=True)
            self.spades_kmers = self._build_spades_kmers(spades_kmers)
            self.spades_use_first_success = spades_use_first_success
            self.careful = careful
            self.only_assembler = only_assembler
        elif self.assembler == 'flye':
            self.canu = external_progs.make_and_check_prog('flye', verbose=self.verbose, required=True)
            self.seqtk= external_progs.make_and_check_prog('seqtk', verbose=self.verbose, required=True)
            self.genomeSize=genomeSize
            self.data_type = data_type
        elif self.assembler == 'racon':
            self.racon = external_progs.make_and_check_prog('racon', verbose=self.verbose, required=True)
            self.minimap2= external_progs.make_and_check_prog('minimap2', verbose=self.verbose, required=True)
            self.miniasm= external_progs.make_and_check_prog('miniasm', verbose=self.verbose, required=True)
            self.awk= external_progs.make_and_check_prog('awk', verbose=self.verbose, required=True)
            self.seqtk= external_progs.make_and_check_prog('seqtk', verbose=self.verbose, required=True)
            #self.minipolish= external_progs.make_and_check_prog('minipolish', verbose=self.verbose, required=True)
            self.data_type = data_type
            self.racon_rounds= racon_rounds
        else:
            raise Error('Unknown assembler: "' + self.assembler + '". cannot continue')



    def _build_spades_kmers(self, kmers):
        if kmers is None:
            return [127,117,107,97,87,77]
        elif type(kmers) == str:
            try:
                kmer_list = [int(k) for k in kmers.split(',')]
            except:
                raise Error('Error getting list of kmers from:' + str(kmers))
            return kmer_list
        elif type(kmers) == list:
            return kmers
        else:
            raise Error('Error getting list of kmers from:' + str(kmers))


    def _make_spades_command(self, kmer, outdir):
        cmd = [
            self.spades.exe(),
            '-s', self.reads,
            '-o', outdir,
            '-t', str(self.threads),
            '-k', str(kmer),
        ]

        if self.careful:
            cmd.append('--careful')

        if self.only_assembler:
            cmd.append('--only-assembler')

        return ' '.join(cmd)


    def _make_canu_command(self, outdir, out_name):
        cmd = [
            self.canu.exe(),
            '-t', str(self.threads),
            '-g', str(float(self.genomeSize)/1000000)+'m',
            '-o', outdir,
            '--'+self.data_type,
            self.reads,
        ]
        return ' '.join(cmd)


    def run_spades_once(self, kmer, outdir):
        cmd = self._make_spades_command(kmer, outdir)
        return common.syscall(cmd, verbose=self.verbose, allow_fail=True)


    def run_spades(self, stop_at_first_success=False):
        '''Runs spades on all kmers. Each a separate run because SPAdes dies if any kmer does
           not work. Chooses the 'best' assembly to be the one with the biggest N50'''
        n50 = {}
        kmer_to_dir = {}

        for k in self.spades_kmers:
            tmpdir = tempfile.mkdtemp(prefix=self.outdir + '.tmp.spades.' + str(k) + '.', dir=os.getcwd())
            kmer_to_dir[k] = tmpdir
            ok, errs = self.run_spades_once(k, tmpdir)
            if ok:
                contigs_fasta = os.path.join(tmpdir, 'contigs.fasta')
                contigs_fai = contigs_fasta + '.fai'
                common.syscall(self.samtools.exe() + ' faidx ' + contigs_fasta, verbose=self.verbose)
                stats = pyfastaq.tasks.stats_from_fai(contigs_fai)
                if stats['N50'] != 0:
                    n50[k] = stats['N50']

                    if stop_at_first_success:
                        break

        if len(n50) > 0:
            if self.verbose:
                print('[assemble]\tkmer\tN50')
                for k in sorted(n50):
                    print('[assemble]', k, n50[k], sep='\t')

            best_k = None

            for k in sorted(n50):
                if best_k is None or n50[k] >= n50[best_k]:
                    best_k = k

            assert best_k is not None

            for k, directory in kmer_to_dir.items():
                if k == best_k:
                    if self.verbose:
                        print('[assemble] using assembly with kmer', k)
                    os.rename(directory, self.outdir)
                else:
                    shutil.rmtree(directory)
        else:
            raise Error('Error running SPAdes. Output directories are:\n  ' + '\n  '.join(kmer_to_dir.values()) + '\nThe reason why should be in the spades.log file in each directory.')


    @classmethod
    def _rename_canu_contigs(cls, infile, outfile):
        with open (infile) as f_in:
            with open(outfile, 'w') as f_out:
                for line in f_in:
                    if line.startswith('>'):
                        print(line.split()[0], file=f_out)
                    else:
                        print(line, end='', file=f_out)


    def run_canu(self):
        '''Runs canu instead of spades'''

        #cmd = self._make_canu_command(self.outdir,'canu')
        cmd = [
            self.canu.exe(),
            '-t', str(self.threads),
            '-g', str(float(self.genomeSize)/1000000)+'m',
            '-o', self.outdir,
            '--'+self.data_type,
            self.reads,
        ]
        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running flye.')

        original_contigs = os.path.join(self.outdir, 'assembly.fasta')
        renamed_contigs = os.path.join(self.outdir, 'contigs.fasta')
        Assembler._rename_canu_contigs(original_contigs, renamed_contigs)
        original_gfa = os.path.join(self.outdir, 'assembly_graph.gfa')
        renamed_gfa = os.path.join(self.outdir, 'contigs.gfa')
        os.rename(original_gfa, renamed_gfa)

    def run_racon(self):
        '''Runs minimap, miniasm, racon instead of spades'''

        if self.data_type.startswith('pacbio'):
            overlap_reads_type = 'ava-pb' # PacBio
        else:
            overlap_reads_type = 'ava-ont' # Nanopore

        if not os.path.exists(self.outdir):
            try:
                os.mkdir(self.outdir)
            except:
                print('Error making output directory', self.outdir, file=sys.stderr)
                sys.exit(1)

            # minimap2
        cmd = [
            self.minimap2.exe(),
            '-t', str(self.threads),
            '-x', overlap_reads_type, self.reads, self.reads,
            '-o', os.path.join(self.outdir, 'output.paf')
        ]

        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running minimap2.')

        # miniasm
        cmd = [
            self.miniasm.exe(),
            '-Rc2', '-f', self.reads, os.path.join(self.outdir, 'output.paf'),
            '>', os.path.join(self.outdir, 'output.gfa')
        ]

        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running miniasm.')

        # gfa2fasta
        cmd = [
            self.awk.exe(),
            '\'/^S/{print ">"$2"\\n"$3}\'', os.path.join(self.outdir, 'output.gfa'),
            '|', 'fold ' '>',  os.path.join(self.outdir, 'output.gfa.fasta')

        ]

        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running awk.')


        if self.data_type.startswith('pacbio'):
            map_reads_type = 'map-pb' # PacBio
        else:
            map_reads_type = 'map-ont' # Nanopore


        # Correction 1
        # minimap2

        cmd = [
            self.minimap2.exe(),
            '-t', str(self.threads),
            '-ax', map_reads_type, '--secondary', 'no', os.path.join(self.outdir, 'output.gfa.fasta'), self.reads,
            '|', self.samtools.exe(), 'view', '-F' ,'0x0900', '-', '>', os.path.join(self.outdir, 'output.gfa1.sam')
        ]
        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running minimap2 correction step #1.')

        # Racon 1
        cmd = [
            self.racon.exe(),
            '-t', str(self.threads), self.reads, os.path.join(self.outdir, 'output.gfa1.sam'),
            os.path.join(self.outdir, 'output.gfa.fasta'),
            '>', os.path.join(self.outdir, 'output.racon1.fasta')
        ]

        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running racon correction step #1.')


        # Correction 2
        # minimap2 2
        cmd = [
            self.minimap2.exe(),
            '-t', str(self.threads),
            '-ax', map_reads_type, '--secondary', 'no', os.path.join(self.outdir, 'output.racon1.fasta'), self.reads,
            '|', self.samtools.exe(), 'view', '-F' ,'0x0900', '-', '>', os.path.join(self.outdir, 'output.gfa2.sam')
        ]

        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running minimap2 correction step #2.')

        # Racon 2
        cmd = [
            self.racon.exe(),
            '-t', str(self.threads), self.reads, os.path.join(self.outdir, 'output.gfa2.sam'),
            os.path.join(self.outdir, 'output.racon1.fasta'),
            '>', os.path.join(self.outdir, 'output.polished.fasta')
        ]

        ok, errs = common.syscall(' '.join(cmd), verbose=self.verbose, allow_fail=False)
        if not ok:
            raise Error('Error running racon correction step #2.')

        original_gfa = os.path.join(self.outdir, 'output.gfa')
        renamed_gfa = os.path.join(self.outdir, 'contigs.gfa')
        os.rename(original_gfa, renamed_gfa)
        original_contigs = os.path.join(self.outdir, 'output.polished.fasta')
        renamed_contigs = os.path.join(self.outdir, 'contigs.fasta')
        Assembler._rename_canu_contigs(original_contigs, renamed_contigs)

    def run(self):
        if self.assembler == 'spades':
            self.run_spades(stop_at_first_success=self.spades_use_first_success)
        elif self.assembler == 'flye':
            self.run_canu()
        elif self.assembler == 'racon':
            self.run_racon()
        else:
            raise Error('Unknown assembler: "' + self.assembler + '". cannot continue')
