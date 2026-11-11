// Décompile les fonctions aux adresses données et écrit le C dans un fichier.
// Usage (headless) : -postScript Decompile.java <sortie.c> <adresse> [<adresse> ...]
// Les adresses sont relatives au module (celles d'objdump sur main.bin / de main.elf).
// @category OoTRR

import java.io.FileWriter;
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class Decompile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        long base = currentProgram.getImageBase().getOffset();
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            out.println("// base du programme dans Ghidra : 0x" + Long.toHexString(base));
            for (int i = 1; i < args.length; i++) {
                Address a = toAddr(base + Long.decode(args[i]));
                Function f = getFunctionContaining(a);
                if (f == null) {
                    disassemble(a);
                    f = createFunction(a, null);
                }
                if (f == null) {
                    out.println("// " + args[i] + " : pas de fonction");
                    continue;
                }
                out.println("// ===== " + args[i] + " -> " + f.getName() + " @ 0x"
                        + Long.toHexString(f.getEntryPoint().getOffset() - base));
                StringBuilder callers = new StringBuilder();
                for (Reference r : getReferencesTo(f.getEntryPoint())) {
                    callers.append(" 0x").append(Long.toHexString(r.getFromAddress().getOffset() - base));
                }
                out.println("// appelée depuis :" + callers);
                DecompileResults res = dec.decompileFunction(f, 120, monitor);
                out.println(res.decompileCompleted() ? res.getDecompiledFunction().getC()
                        : "// échec : " + res.getErrorMessage());
            }
        }
    }
}
