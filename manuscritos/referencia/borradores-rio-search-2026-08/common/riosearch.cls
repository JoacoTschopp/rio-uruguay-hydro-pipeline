% riosearch.cls -- clase LaTeX comun de Rio_Search (Fase 8, docs/rio_search_plan.md S3.11).
%
% Extraida de `rio_search/research/templates/FINAL-G1-TSCHOPP-JOAQUIN-2025.tex` (el trabajo con
% formato ya validado y presentado por el usuario, decision #8 del plan): mismo documentclass
% base (report, 11pt), mismos paquetes, misma geometria (margenes 3cm), mismo interlineado
% (onehalfspacing) y mismo estilo de portada (escudo + Universidad de Buenos Aires + Facultad de
% Ciencias Exactas y Naturales + Maestria en Explotacion de Datos y Descubrimiento de
% Conocimiento). Lo unico que cambia es que la portada queda parametrizada por comandos
% (\riosearchtitle, \riosearchauthor, ...) en vez de texto fijo, para poder reusarla en dos
% documentos (thesis/proyecto/ y thesis/tesis/) con el mismo formato.
%
% Nota para el usuario (§8 del plan, "dependencias del usuario"): la institucion/carrera de la
% portada se copio tal cual del modelo (UBA / FCEN / Maestria en Explotacion de Datos y
% Descubrimiento de Conocimiento) asumiendo que es el mismo programa de esta tesis -- confirmar
% que aplica igual antes de la entrega final.

\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{riosearch}[2026/08/27 Rio_Search thesis class]

% El modelo declara metadatos de PDF (pdftitle/pdfauthor/pdfcreator) directamente en las opciones
% de \documentclass; aca se resuelven via hyperref (\riosearchtitle/\riosearchauthor los setean).
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{report}}
\ProcessOptions\relax
\LoadClass[11pt]{report}

% ---------------------------------------------------------------------------
% Paquetes (mismo conjunto que el modelo, sin las duplicaciones que tenia el .tex original)
% ---------------------------------------------------------------------------
\RequirePackage[utf8]{inputenc}
\RequirePackage[spanish]{babel}
\RequirePackage[T1]{fontenc}
\RequirePackage{lmodern}
\RequirePackage{geometry}
\RequirePackage{setspace}
\RequirePackage{hyperref}
\RequirePackage{longtable}
\RequirePackage{booktabs}
\RequirePackage{upgreek}
\RequirePackage{amsmath}
\RequirePackage{textcomp}
\RequirePackage{graphicx}
\RequirePackage{subcaption}
\RequirePackage{enumitem}
% El modelo carga apacite (estilo APA, exigido por la carrera) y natbib juntos -- combinacion no
% recomendada por apacite pero es la que el usuario ya probo y compilo (`research/templates/*.bbl`
% existe): se replica tal cual para no arriesgar un comportamiento de citas distinto al validado.
\RequirePackage{apacite}
\RequirePackage{natbib}
\RequirePackage{float}

\geometry{left=3cm, right=3cm, top=3cm, bottom=3cm}
\onehalfspacing

\hypersetup{
  colorlinks=true,
  linkcolor=black,
  citecolor=black,
  urlcolor=blue,
}

% ---------------------------------------------------------------------------
% Portada parametrizada (§3.11: "portada" extraida del modelo, con titulo/autor/fecha de
% Rio Uruguay en vez del tema anterior -- lago/cianobacterias)
% ---------------------------------------------------------------------------
\newcommand{\riosearchinstitution}{Universidad de Buenos Aires}
\newcommand{\riosearchfaculty}{Facultad de Ciencias Exactas y Naturales}
\newcommand{\riosearchprogram}{Maestr\'ia en Explotaci\'on de Datos y Descubrimiento de Conocimiento}
\newcommand{\riosearchlogo}{../common/img/escudo_uba.png}

% Etapa del documento: "Proyecto de Tesis" o "Tesis" (§3.11: dos documentos, mismo formato)
\newcommand{\riosearchstagename}{Tesis}
\newcommand{\riosearchstage}[1]{\renewcommand{\riosearchstagename}{#1}}

\newcommand{\riosearchdoctitle}{}
\newcommand{\riosearchtitle}[1]{\renewcommand{\riosearchdoctitle}{#1}}

\newcommand{\riosearchdocauthor}{}
\newcommand{\riosearchauthor}[1]{\renewcommand{\riosearchdocauthor}{#1}}

\newcommand{\riosearchdocdirector}{}
\newcommand{\riosearchdirector}[1]{\renewcommand{\riosearchdocdirector}{#1}}

\newcommand{\riosearchdocyear}{\the\year}
\newcommand{\riosearchyear}[1]{\renewcommand{\riosearchdocyear}{#1}}

\newcommand{\makeriosearchcover}{%
  \begin{titlepage}
    \begin{center}
      \IfFileExists{\riosearchlogo}{\includegraphics[width=5cm]{\riosearchlogo}\\[1cm]}{}

      {\Large \textbf{\riosearchinstitution}}\\[0.2cm]
      \textbf{\riosearchfaculty}\\[0.2cm]
      \textbf{\riosearchprogram}\\[2cm]

      {\large \textbf{\riosearchstagename}}\\[1cm]

      {\Huge \textbf{\riosearchdoctitle}}\\[4cm]

      \riosearchdocauthor\\[0.5cm]
      \ifx\riosearchdocdirector\empty\else
        Director: \riosearchdocdirector\\[0.5cm]
      \fi

      {\normalsize \textbf{\riosearchdocyear}}
    \end{center}
  \end{titlepage}
}

% Estilo de bibliografia consistente con `thesis/common/references.bib` (Fase 7, ExportBibtex):
% el modelo usa apacite (estilo APA, exigido por la carrera); las entradas @article que genera
% `BibtexExporter` (title/author/year/journal/url) son compatibles.
%
% `\bibliography{references}` va SIN ruta relativa a proposito (hallazgo real, Fase 8): con
% `latexmk -outdir=build`, `bibtex` corre con el directorio de trabajo cambiado a `build/`, pero
% el chequeo previo de latexmk de que el .bib existe se hace relativo al directorio del .tex
% principal (`thesis/{proyecto,tesis}/`) -- las dos bases no coinciden, asi que ninguna ruta
% relativa fija (`../common/…` ni `../../common/…`) sirve para las dos a la vez. La resolucion es
% que cada documento agregue `thesis/common/` a `BIBINPUTS` en su propio `.latexmkrc`
% (`thesis/tesis/.latexmkrc` / `thesis/proyecto/.latexmkrc`): con eso, un nombre sin ruta lo
% encuentra kpathsea sin importar el directorio de trabajo real en cada paso.
\newcommand{\riosearchbibliography}{%
  \bibliographystyle{apacite}
  \bibliography{references}
}
