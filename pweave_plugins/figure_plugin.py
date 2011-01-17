"""
This module defines a Matplotlib-figure processor class for use with Pweave.

2011-01-14, Mark Edgington

"""
# this plugin module is only imported by Pweave.py
import __main__ as pweave
CodeProcessor = pweave.CodeProcessor

from string import Template
import os
import matplotlib.pyplot as plt

class MatplotlibFigureProcessor(CodeProcessor):
    """Processor for generating (LaTeX) figures from matplotlib plots.
    
    Given a code-block containing sourcecode required to generate a matplotlib
    figure, a PDF file of this figure will be stored, and the LaTeX snippet
    required for including the image in a LaTeX figure will be generated. 
    
    The following code-block options are accepted:
    
    *output_folder* -- specifies the folder (relative to the Pweave source
                       file if not given as an absolute path) which should be
                       used for storing the generated image pdf files. This
                       folder will be created if it doesn't already exist. The
                       default folder is 'images'.

    *filename* -- specifies the basename of the pdf file which will be stored
                  in *output_folder*.  By default this will be "FigureNNN",
                  where NNN is some number.
    
    *width* -- specifies (in any valid LaTeX units) the image
               width.  The default is "0.9\linewidth".
               
    *height* -- specifies (in any valid LaTeX units) the image height
                If height is not specified, only width is used.
    
    *center* -- should the figure be centered? (true/false). Default=true
    
    *caption* -- the figure caption. (Defaults to "")
    
    *label* -- the name of the LaTeX label to use (if not provided, no label
               will be associated with the figure).
    
    *where* -- string indicating where to place the figure (default='h').
    
    TODO: other formatting options
    
    """
    def __init__(self):
        super(MatplotlibFigureProcessor, self).__init__()
        self.figure_number = 1 # counter used for autogenerating figure-names
        
    def name(self):
        return "mplfig"
    
    def default_block_options(self):
        "Return a dictionary containing the processor's default block-options."
        option_defaults = {
                            'output_folder': 'images',
                            'filename': None,
                            'width': None,
                            'height': None,
                            'center': 'true',
                            'caption': '',
                            'label': None,
                            'where': 'h',
                            'echo': 'false',
                          }
        
        return option_defaults


    def output_template_str(self):
        return r'''
\begin{figure}[$where]
 $centering
 \includegraphics[$dimensions]{$imgfile}
 \caption{$caption}
 $label
\end{figure}
'''

    def get_image_path(self, outfolder):
        "Autogenerate an image path."
        fname = "mpl_image_%03d.pdf" % self.figure_number
        imgpath = os.path.join(outfolder, fname)
        
        return imgpath
        

    def get_substitution_dict(self, codeblock_options):
        "populate variables for substitution"
        o = codeblock_options
        s = substitution_vars = {}
        
        for k in ['width', 'caption', 'where']:
            s[k] = o[k]
        
        
        #r'0.9\linewidth',
        dimensions = []
        heightset = (o['height'] is not None)
        widthset = (o['width'] is not None)
        
        if widthset:
            dimensions.append('width=' + o['width'])
        if heightset:
            dimensions.append('height=' + o['height'])
        if not widthset and not heightset:
            dimensions.append(r'width=0.9\linewidth')

        s['dimensions'] = ",".join(dimensions)
        
        if o['label'] is not None:
            s['label'] = r'\label{' + o['label'] + '}\n'
        else:
            s['label'] = ''
        
        if o['center'].lower() == 'true':
            s['centering'] = r'\centering'
        else:
            s['centering'] = ''
        
        outfolder = os.path.join(self.parentdir, o['output_folder'])
        if o['filename'] is not None:
            s['imgfile'] = os.path.join(outfolder, o['filename'])
        else:
            # auto-generate filename
            s['imgfile'] = self.get_image_path(outfolder)
        
        return substitution_vars
    
    def write_figure(self, filename):
        "Write (and clear) the matplotlib fig as a pdf to the specified file."
        plt.savefig(filename, dpi = 200)
        plt.clf()
        
    
    def process_code(self, codeblock, codeblock_options):
        substitution_vars = self.get_substitution_dict(codeblock_options)
        
        # execute the codeblock, storing results in self.execution_namespace
        self.exec_code(codeblock)
        self.write_figure(substitution_vars['imgfile'])

        document_text = \
            Template(self.output_template_str()).substitute(substitution_vars)
        
        # by default, don't echo the codeblock to the output document
        if codeblock_options['echo'].lower() == 'true':
            code_text = codeblock
        else:
            code_text = ''
            
        self.figure_number += 1
        
        return (document_text, code_text)