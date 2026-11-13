cwlVersion: v1.2
class: CommandLineTool
baseCommand: [sh, -c]
arguments:
  - |
    mkdir -p alignments multiqc pipeline_info counts
    printf 'bam' > alignments/s1.bam; printf 'ix' > alignments/s1.bam.bai
    printf 'bam' > alignments/s2.bam; printf 'ix' > alignments/s2.bam.bai
    printf 'g\t1\n' > counts/s1.tsv
    printf '<html></html>' > multiqc/multiqc_report.html
    printf '<html></html>' > 'pipeline_info/report #1.html'
    printf '2' > passed.txt
inputs: []
outputs:
  qc_report:
    type: File
    outputBinding: {glob: multiqc/multiqc_report.html}
  alignments:
    type: File[]
    secondaryFiles: [.bai]
    outputBinding: {glob: alignments/*.bam}
  gene_counts:
    type: Directory
    outputBinding: {glob: counts}
  samples_passed_qc:
    type: int
    outputBinding:
      glob: passed.txt
      loadContents: true
      outputEval: $(parseInt(self[0].contents))
  pipeline_report:
    type: File
    outputBinding: {glob: 'pipeline_info/report #1.html'}
  missing_optional:
    type: File?
    outputBinding: {glob: missing.txt}
requirements:
  InlineJavascriptRequirement: {}
