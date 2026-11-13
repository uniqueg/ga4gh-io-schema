version 1.0

workflow rnaseq {
  input {
    Array[String] samples = ["s1", "s2"]
  }
  scatter (sample in samples) {
    call align { input: sample = sample }
  }
  call qc { input: bams = align.bam }
  output {
    File qc_report = qc.report
    Array[File] alignments = align.bam
    Map[String, File] gene_counts = qc.counts
    File? optional_plot = qc.plot
    Int samples_passed_qc = qc.passed
    File debug_log = qc.log
  }
}

task align {
  input {
    String sample
  }
  command <<<
    printf 'bam' > ~{sample}.bam
  >>>
  output {
    File bam = "~{sample}.bam"
  }
}

task qc {
  input {
    Array[File] bams
  }
  command <<<
    printf '<html></html>' > multiqc_report.html
    printf 'g\t1\n' > s1.tsv
    printf 'debug' > debug.log
    printf '2' > passed.txt
  >>>
  output {
    File report = "multiqc_report.html"
    Map[String, File] counts = {"s1": "s1.tsv"}
    File? plot = "plot.png"
    Int passed = read_int("passed.txt")
    File log = "debug.log"
  }
}
