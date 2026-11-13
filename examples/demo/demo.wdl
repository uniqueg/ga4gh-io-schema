# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

version 1.1

# The demo workflow of the GA4GH I/O Schema (see docs/adoption/demo.md):
# filters, sorts and indexes aligned reads, and writes an HTML report.
# Its I/O Schema, ga4gh-io.schema.json, is generated from this document by
# build_schema.py; change both together.

workflow io_schema_demo {
  meta {
    description: "Filters aligned reads by mapping quality and flags, sorts and indexes them, and reports alignment statistics."
  }

  input {
    File reads
    Int min_mapq = 0
    String read_filter = "none"
  }

  parameter_meta {
    reads: {
      label: "Aligned reads (BAM)",
      description: "Reads aligned to a reference, in BAM format, in any order."
    }
    min_mapq: {
      label: "Minimum mapping quality",
      description: "Reads with a lower mapping quality are removed (0 keeps all reads)."
    }
    read_filter: {
      label: "Read filter",
      description: "Which reads to keep besides the mapping quality: all, properly paired only, or primary alignments only.",
      choices: ["none", "proper_pairs", "primary_only"]
    }
    filtered_bam: {
      label: "Filtered reads (BAM)",
      description: "The filtered reads, sorted by coordinate."
    }
    filtered_bam_index: {
      label: "Index of the filtered reads (BAI)",
      description: "The index of the filtered reads."
    }
    report: {
      label: "Alignment report (HTML)",
      description: "Statistics of the reads before and after filtering."
    }
  }

  call filter_sort_index {
    input:
      reads = reads,
      min_mapq = min_mapq,
      read_filter = read_filter
  }

  call make_report {
    input:
      reads = reads,
      filtered_bam = filter_sort_index.bam,
      min_mapq = min_mapq,
      read_filter = read_filter
  }

  output {
    File filtered_bam = filter_sort_index.bam
    File filtered_bam_index = filter_sort_index.bai
    File report = make_report.html
  }
}

task filter_sort_index {
  input {
    File reads
    Int min_mapq
    String read_filter
  }

  command <<<
    set -euo pipefail
    case "~{read_filter}" in
      none) flags="" ;;
      proper_pairs) flags="-f 2" ;;
      primary_only) flags="-F 0x900" ;;
      *) echo "Unknown read filter: ~{read_filter}" >&2; exit 1 ;;
    esac
    # shellcheck disable=SC2086
    samtools view -b -q ~{min_mapq} $flags "~{reads}" \
      | samtools sort -o filtered.bam -
    samtools index filtered.bam filtered.bam.bai
  >>>

  output {
    File bam = "filtered.bam"
    File bai = "filtered.bam.bai"
  }

  runtime {
    docker: "quay.io/biocontainers/samtools:1.24--h9dcdb79_1"
    cpu: 1
    memory: "1 GiB"
  }
}

task make_report {
  input {
    File reads
    File filtered_bam
    Int min_mapq
    String read_filter
  }

  command <<<
    set -euo pipefail
    samtools flagstat "~{reads}" > before.txt
    samtools flagstat "~{filtered_bam}" > after.txt
    {
      echo '<!DOCTYPE html>'
      echo '<html lang="en"><head><meta charset="utf-8">'
      echo '<title>Alignment report</title></head><body>'
      echo '<h1>Alignment report</h1>'
      echo '<p>Minimum mapping quality: ~{min_mapq}; read filter: ~{read_filter}.</p>'
      echo '<h2>Before filtering</h2><pre>'
      sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' before.txt
      echo '</pre><h2>After filtering</h2><pre>'
      sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g' after.txt
      echo '</pre></body></html>'
    } > report.html
  >>>

  output {
    File html = "report.html"
  }

  runtime {
    docker: "quay.io/biocontainers/samtools:1.24--h9dcdb79_1"
    cpu: 1
    memory: "1 GiB"
  }
}
