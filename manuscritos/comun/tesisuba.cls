% tesisuba.cls -- clase comun de los manuscritos (plan de tesis y tesis).
%
% Formato tomado del trabajo ya presentado y validado por la carrera:
%   manuscritos/referencia/tfi-especializacion-2025/FINAL-G1-TSCHOPP-JOAQUIN-2025.tex
% Mismo documentclass base (report, 11pt), mismos paquetes, margenes de 3cm, interlineado 1,5,
% estilo APA (apacite) y la misma portada. La diferencia es que los datos de la portada son
% comandos, para usar la misma clase en los dos documentos.
%
% Antecedente: rio_search/thesis/common/riosearch.cls (rama feature/rio-search), copiado sin
% cambios en manuscritos/referencia/borradores-rio-search-2026-08/common/.
%
% El archivo fuente se guarda en ASCII a proposito: los acentos van como \'a, \~n, etc.

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{tesisuba}[2026/09/16 Manuscritos de tesis UBA FCEN]

\DeclareOption*{\PassOptionsToClass{\CurrentOption}{report}}
\ProcessOptions\relax
\LoadClass[11pt,a4paper]{report}

% ---------------------------------------------------------------------------
% Paquetes: los del modelo validado, sin las cargas duplicadas que tenia su .tex
% ---------------------------------------------------------------------------
\RequirePackage[utf8]{inputenc}
\RequirePackage[spanish]{babel}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern}
\RequirePackage{geometry}
\RequirePackage{setspace}
\RequirePackage{longtable}
\RequirePackage{booktabs}
\RequirePackage{upgreek}
\RequirePackage{amsmath}
\RequirePackage{textcomp}
\RequirePackage{graphicx}
\RequirePackage{subcaption}
\RequirePackage{enumitem}
% El modelo carga apacite y natbib juntos. apacite recomienda la opcion [natbibapa] en su lugar;
% se replica lo validado y no se cambia sin compilar y comparar contra el PDF de referencia.
\RequirePackage{apacite}
\RequirePackage{natbib}
\RequirePackage{float}
\RequirePackage{hyperref}

\geometry{a4paper, left=3cm, right=3cm, top=3cm, bottom=3cm}
\onehalfspacing

% Sin \hypersetup: el PDF validado usa los valores por defecto de hyperref (recuadros en los
% enlaces, que no se imprimen). Si se prefieren enlaces sin recuadro: \hypersetup{hidelinks}.

\graphicspath{{./figuras/}{../comun/img/}}

% ---------------------------------------------------------------------------
% Datos de portada
% ---------------------------------------------------------------------------
% Van con \newcommand* (no \long) para que \ifx\campo\empty detecte bien un campo vacio.
\newcommand*{\tu@institucion}{Universidad de Buenos Aires}
\newcommand*{\tu@facultad}{Facultad de Ciencias Exactas y Naturales}
\newcommand*{\tu@carrera}{Maestr\'ia en Explotaci\'on de Datos y Descubrimiento de Conocimiento}
\newcommand*{\tu@etapa}{}
\newcommand*{\tu@titulo}{}
\newcommand*{\tu@autor}{}
\newcommand*{\tu@director}{}
\newcommand*{\tu@codirector}{}
\newcommand*{\tu@lugar}{}
\newcommand*{\tu@anio}{\the\year}

\newcommand*{\carrera}[1]{\renewcommand*{\tu@carrera}{#1}}
\newcommand*{\etapa}[1]{\renewcommand*{\tu@etapa}{#1}}
\newcommand*{\titulo}[1]{\renewcommand*{\tu@titulo}{#1}}
\newcommand*{\autor}[1]{\renewcommand*{\tu@autor}{#1}}
\newcommand*{\director}[1]{\renewcommand*{\tu@director}{#1}}
\newcommand*{\codirector}[1]{\renewcommand*{\tu@codirector}{#1}}
\newcommand*{\lugardetrabajo}[1]{\renewcommand*{\tu@lugar}{#1}}
\newcommand*{\anio}[1]{\renewcommand*{\tu@anio}{#1}}

% Portada del modelo validado: escudo, 1cm, institucion, 3cm, titulo, 6cm, autor, 0.5cm, anio.
% Los campos etapa/director/codirector/lugar no estaban en el modelo: si se completan, se acortan
% los espacios para que la portada siga entrando en una hoja.
\newlength{\tu@antesdeltitulo}
\newlength{\tu@antesdelautor}
\newcommand{\portada}{%
  \setlength{\tu@antesdeltitulo}{3cm}%
  \setlength{\tu@antesdelautor}{6cm}%
  \ifx\tu@etapa\empty\else\setlength{\tu@antesdeltitulo}{1.5cm}\setlength{\tu@antesdelautor}{4cm}\fi
  \ifx\tu@director\empty\else\setlength{\tu@antesdelautor}{3cm}\fi
  \begin{titlepage}
    \begin{center}
      \includegraphics[width=5cm]{escudo_uba.png}\\[1cm]

      {\Large \textbf{\tu@institucion}}\\[0.2cm]
      \textbf{\tu@facultad}\\[0.2cm]
      \textbf{\tu@carrera}\\[\tu@antesdeltitulo]

      \ifx\tu@etapa\empty\else
        {\large \textbf{\tu@etapa}}\\[1cm]
      \fi

      {\Huge \textbf{\tu@titulo}}\\[\tu@antesdelautor]

      \tu@autor\\[0.5cm]
      \ifx\tu@director\empty\else
        Director: \tu@director\\[0.2cm]
      \fi
      \ifx\tu@codirector\empty\else
        Codirector: \tu@codirector\\[0.2cm]
      \fi
      \ifx\tu@lugar\empty\else
        Lugar de trabajo: \tu@lugar\\[0.5cm]
      \fi

      {\normalsize \textbf{A\~no \tu@anio}}
    \end{center}
  \end{titlepage}
}

% ---------------------------------------------------------------------------
% Bibliografia
% ---------------------------------------------------------------------------
% Como en el modelo, la bibliografia no se agrega al indice y usa apacite.
%
% `referencias` va sin ruta: herramientas/compilar.ps1 agrega manuscritos/comun/ a BIBINPUTS.
% Con salida en build/, bibtex no resuelve una ruta relativa fija igual que pdflatex (hallazgo de
% la Fase 8 de Rio_Search, rama feature/rio-search).
\newcommand{\bibliografia}{%
  \cleardoublepage
  \bibliographystyle{apacite}
  \bibliography{referencias}
}
