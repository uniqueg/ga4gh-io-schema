version 1.1

task count {
  input {
    File reads
    String label
    Int threads = 1
  }

  parameter_meta {
    threads: "Threads of the count."
  }

  command <<<
    wc -l ~{reads} > out
  >>>

  output {
    File out = "out"
  }
}
