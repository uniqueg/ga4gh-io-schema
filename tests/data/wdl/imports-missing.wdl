version 1.0

# Imports a document that doesn't exist, for the converter tests.

import "missing/t.wdl"

workflow w {
  call t.t
}
