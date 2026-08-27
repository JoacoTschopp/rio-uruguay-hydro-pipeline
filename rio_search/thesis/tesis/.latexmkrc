# .latexmkrc de thesis/tesis/ (Fase 8, docs/rio_search_plan.md S3.11): agrega thesis/common/ al
# search path de BibTeX (BIBINPUTS) para que `\bibliography{references}` (riosearch.cls, sin ruta
# relativa) encuentre thesis/common/references.bib sin importar si bibtex corre en este directorio
# o en build/ (latexmk -outdir=build cambia el directorio de trabajo solo para bibtex, no para
# pdflatex -- ver comentario en thesis/common/riosearch.cls).
#
# Correr con PowerShell nativo (Decision 049, docs/decisions.md): Git Bash/MSYS reescribe rutas y
# bibtex.exe (MiKTeX) no las resuelve.
use Cwd;
my $common_dir = Cwd::abs_path("../common");
$ENV{'BIBINPUTS'} = "$common_dir;" . ($ENV{'BIBINPUTS'} // '');
