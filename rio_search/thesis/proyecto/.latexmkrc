# .latexmkrc de thesis/proyecto/ -- ver comentario en thesis/tesis/.latexmkrc (mismo mecanismo,
# mismo directorio thesis/common/ compartido por los dos documentos).
use Cwd;
my $common_dir = Cwd::abs_path("../common");
$ENV{'BIBINPUTS'} = "$common_dir;" . ($ENV{'BIBINPUTS'} // '');
