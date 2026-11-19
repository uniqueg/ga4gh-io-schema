#!/usr/bin/env cwl-runner
# A tool that uses every construct the converter maps (it doesn't run).
cwlVersion: v1.2
class: CommandLineTool
$namespaces:
  edam: http://edamontology.org/
label: Call variants
doc:
  - Align reads to a reference genome and call variants.
  - Used to test the CWL converter.
requirements:
  SchemaDefRequirement:
    types:
      - $import: call-variants-types.yml
      - name: Caller
        type: enum
        label: Variant caller
        symbols: [gatk, bcftools, freebayes]
inputs:
  reference:
    type: File
    label: Reference genome
    doc: FASTA file of the reference genome, indexed with samtools and BWA.
    format: edam:format_1929
    secondaryFiles:
      - .fai
      - pattern: ^.dict
        required: true
      - pattern: .amb
        required: false
      - .ann?
      - $(self.nameroot).bwt
  samples:
    type: call-variants-types.yml#Sample[]
    label: Samples
  caller:
    type: "#Caller"
    default: gatk
  regions:
    type: File?
    label: Regions
    doc: BED file of the regions to call variants in.
    format: edam:format_3003
  known_sites:
    type: File
    format: edam:format_3016
    secondaryFiles: [.tbi]
    default:
      class: File
      location: https://data.example.org/known-sites.vcf.gz
  blacklist:
    type: File
    default:
      class: File
      location: blacklist.bed
  annotation_dir: Directory?
  min_quality:
    type: double
    default: 20.5
  max_depth: long?
  threads:
    type: int
    default: 4
  emit_all: boolean?
  tags:
    type: string[]
    default: [variants, test]
  ploidy:
    type: [int, string]
  extra_config:
    type: ["null", File, string]
  options: Any
  stdin_reads: stdin
outputs:
  log: stdout
  variants:
    type: File
    format: edam:format_3016
    secondaryFiles:
      - pattern: .tbi
        required: true
      - .csi
    outputBinding: {glob: calls.vcf.gz}
  alignments:
    type: File[]
    format: $(inputs.reference.format)
    outputBinding: {glob: "*.bam"}
  summary:
    type:
      type: record
      name: Summary
      label: Summary of the calls
      fields:
        - name: report
          type: File
          format: edam:format_2331
          outputBinding: {glob: report.html}
        - name: count
          type: int?
          outputBinding:
            glob: count.txt
            loadContents: true
            outputEval: $(parseInt(self[0].contents))
  coverage:
    type: File?
    outputBinding: {glob: coverage.txt}
baseCommand: call-variants
