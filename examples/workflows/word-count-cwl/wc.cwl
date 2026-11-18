# SPDX-FileCopyrightText: 2026 ELIXIR On-Cloud <cloud-service@elixir-europe.org>
#
# SPDX-License-Identifier: Apache-2.0

# A seeded workflow of the demo (see docs/adoption/testbed.md): counts the
# lines, words or characters of a text file. Never run by the testbed.
cwlVersion: v1.2
class: CommandLineTool
label: Count words
doc: Counts the lines, words or characters of a text file with wc.
requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: docker.io/library/busybox:1.37
baseCommand: wc
inputs:
  text:
    type: File
    label: Text file
    doc: A plain text file.
    format: http://edamontology.org/format_2330
    inputBinding:
      position: 2
  unit:
    type:
      type: enum
      symbols: [lines, words, characters]
    label: What to count
    default: words
    inputBinding:
      position: 1
      valueFrom: "$({lines: '-l', words: '-w', characters: '-c'}[self])"
stdout: count.txt
outputs:
  count:
    type: File
    label: Count
    doc: The count and the name of the file, as wc prints them.
    outputBinding:
      glob: count.txt
