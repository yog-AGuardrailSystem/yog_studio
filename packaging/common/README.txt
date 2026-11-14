yogc - the YOG policy compiler
==============================

YOG is a small, deterministic policy language: for every action an AI agent wants to take it answers ALLOW or DENY,
the same way every time, with the reason. yogc is its compiler and engine (lexer, parser, semantic analysis, clause
table, VM), written in C11 by the YOG engine team.

Version: built from yog_engine commit @COMMIT@ (the same engine YOG Studio uses).

Try it (from the folder that contains policy.yog, in examples/ after installing):

    yogc check policy.yog alice can_delete database_1          prints ALLOW|<reason>
    yogc check policy.yog bob can_delete database_1 --trace    shows how the decision was reached
    yogc check policy.yog alice can_delete db --context "fact environment(db, production)"

Commands:

    yogc check POLICY ACTOR ACTION RESOURCE [--context "fact a(b); fact c(d)"] [--trace]
    yogc batch POLICY [--trace]      one request per line on stdin:  actor action resource [| context]
    yogc run   POLICY [--trace]      run every `query` in the file
    yogc ir    POLICY                print the compiled clause table

Exit status: 0 allowed / ok, 3 denied, 1 the policy does not compile, 2 usage or file error.
Rules: DENY beats ALLOW, and anything not allowed is denied. An error never gives ALLOW.

Note: context facts are split at every ';' (even inside quotes). Only pass context you build yourself; never pass raw
text from users or from a model.

This build is not code-signed, so Windows may show "unknown publisher". On PCs with Smart App Control enforced Windows
blocks unsigned programs; use the Linux build (also under WSL) or build from source:

    cc -std=c11 -O2 -I src -I include src/lexer/lexer.c src/parser/*.c src/sema/*.c src/ir/*.c src/vm/*.c src/api/yog.c tools/yogc.c -o yogc

License: MIT (see LICENSE.txt). Source: https://github.com/yog-AGuardrailSystem/yog_engine
