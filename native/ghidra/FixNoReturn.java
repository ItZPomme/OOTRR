// Retire le marquage « ne revient jamais » des fonctions qui contiennent un RET, un saut
// indirect (BR, appel terminal) ou un saut direct vers une autre fonction.
// L'analyse automatique de Ghidra se trompe souvent sur ce binaire (allocateur, etc.),
// ce qui coupe la décompilation des fonctions appelantes.
// Usage (headless, sans -readOnly) : -postScript FixNoReturn.java
// @category OoTRR

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

public class FixNoReturn extends GhidraScript {
    @Override
    public void run() throws Exception {
        int fixed = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            if (!f.hasNoReturn()) {
                continue;
            }
            InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
            while (it.hasNext()) {
                Instruction ins = it.next();
                String m = ins.getMnemonicString().toLowerCase();
                boolean tail = m.equals("b") && ins.getFlows().length == 1
                        && !f.getBody().contains(ins.getFlows()[0]);
                if (m.startsWith("ret") || m.startsWith("br") || tail) {
                    f.setNoReturn(false);
                    fixed++;
                    break;
                }
            }
        }
        println("FixNoReturn : " + fixed + " fonctions corrigées");
    }
}
