// Réglages d'analyse pour main.elf, à passer en -preScript à l'import.
// Le détecteur de fonctions « qui ne reviennent jamais » se trompe sur ce binaire
// (l'allocateur finit par un appel terminal) et coupe le code après chaque appel.
// @category OoTRR

import ghidra.app.script.GhidraScript;

public class SetupAnalysis extends GhidraScript {
    @Override
    public void run() throws Exception {
        setAnalysisOption(currentProgram, "Non-Returning Functions - Discovered", "false");
        println("SetupAnalysis : détection des fonctions sans retour désactivée");
    }
}
