// SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
//
// SPDX-License-Identifier: Apache-2.0

// A seeded workflow of the demo (see docs/adoption/testbed.md): greets
// people, in one of a few languages. Never run by the testbed.
nextflow.enable.dsl = 2

params.names = ['Ada', 'Grace']
params.language = 'en'
params.times = 1
params.shout = false
params.outdir = 'results'

def GREETINGS = [en: 'Hello', de: 'Hallo', fr: 'Bonjour', it: 'Ciao']

process GREET {
    publishDir params.outdir, mode: 'copy'
    input:
    val name
    output:
    path "${name}.txt"
    script:
    def text = "${GREETINGS[params.language]}, ${name}!"
    def line = params.shout ? text.toUpperCase() : text
    """
    for i in \$(seq ${params.times}); do echo '${line}'; done > '${name}.txt'
    """
}

workflow {
    GREET(Channel.fromList(params.names))
}
