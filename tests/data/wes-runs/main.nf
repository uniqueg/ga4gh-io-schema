nextflow.enable.dsl = 2

params.outdir = 'results'

process ALIGN {
    publishDir "${params.outdir}/alignments", mode: 'copy'
    input:
    val sample
    output:
    path "${sample}.bam*"
    script:
    """
    printf 'bam' > ${sample}.bam
    printf 'ix' > ${sample}.bam.bai
    """
}

process COUNT {
    publishDir "${params.outdir}/counts", mode: 'copy'
    output:
    path 's1.tsv'
    script:
    """
    printf 'g\\t1\\n' > s1.tsv
    """
}

process MULTIQC {
    publishDir "${params.outdir}/multiqc", mode: 'copy'
    output:
    path 'multiqc_report.html'
    script:
    """
    printf '<html></html>' > multiqc_report.html
    """
}

process PIPELINE_INFO {
    publishDir "${params.outdir}/pipeline_info", mode: 'copy'
    output:
    path 'report #1.html'
    script:
    """
    printf '<html></html>' > 'report #1.html'
    """
}

workflow {
    ALIGN(Channel.of('s1', 's2'))
    COUNT()
    MULTIQC()
    PIPELINE_INFO()
}
