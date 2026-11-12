version 1.1

# Every WDL type, with defaults and parameter_meta, for the converter tests.

import "tasks/count.wdl" as count

struct Sample {
  String id
  File? reads
  Array[Int]+ lanes
}

workflow types {
  meta {
    description: "Every WDL type."
    allowNestedInputs: true
  }

  parameter_meta {
    name: "Name of the run."
    mode: {
      description: "Mode of the run.",
      help: "Fast skips the QC.",
      label: "Mode",
      choices: ["fast", "full"],
      suggestions: ["fast"]
    }
    threads: { description: "Threads.", category: "advanced", choices: [] }
    reads: { description: "Reads.", choices: ["a.fq"], patterns: ["*.fq"] }
    scale: [1, 2]
    report: { description: "The report.", choices: ["x"] }
  }

  input {
    String name
    String mode = "fast"
    Int threads = 4
    Float scale = 1
    Boolean verbose = false
    File reads
    File reference = "https://example.org/ref.fa"
    File local = "data/ref.fa"
    File? optional_reads
    Array[File]+ lanes
    Array[String?] tags = []
    Array[File] extra = []
    Array[File] more = ["a.txt"]
    Map[String, Int] counts = {"a": 1}
    Map[File, String] by_file = {}
    Pair[Int, File] pair
    Sample sample
    String derived = name + ".out"
    String? nothing = None
  }

  call count.count as counter { input: reads = reads }

  output {
    File report = counter.out
    File? maybe = optional_reads
    Array[String] names = [name]
  }
}
