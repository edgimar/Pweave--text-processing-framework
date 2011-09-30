import os
import sys
import re
import StringIO
import code
import inspect
from . import formatters
try:
    from pygments import highlight
    from pygments.lexers import PythonLexer
    from pygments.formatters import HtmlFormatter, LatexFormatter
except:
    pass


def pweave(file, doctype = 'tex', returnglobals = True, plot = True): 
    """Process a noweb python document and write output to a file"""  
    doc = Pweb(file)
    
    #Set options
    doc.setformat(doctype)
    if sys.platform == 'cli':
        doc.usesho = plot
    else:
        doc.usematplotlib = plot
    
    try:
        doc.weave()
        if returnglobals:
        #Get the calling scope and return results to its globals
        #this way you can modify the weaved variables from repl
            _returnglobals()
    except Exception as inst:
        sys.stderr.write('%s\n%s\n' % (type(inst), inst.args))
        #Return varibles used this far if there is an exception
        if returnglobals:
            _returnglobals()
 
def _returnglobals():
    """Inspect stack to get the scope of the terminal/script calling pweave function"""
    if hasattr(sys,'_getframe'):
        caller = inspect.stack()[2][0]
        caller.f_globals.update(Pweb.globals)
    if not hasattr(sys,'_getframe'):
        print('%s\n%s\n' % ("Can't return globals" ,"Start Ironpython with ipy -X:Frames if you wan't this to work"))
                 
class Pweb(object):
    
    #Shared across class instances
    globalformatdict = None
    chunkformatters = []
    chunkprocessors = []
    globals = {}
    figdir = ''
    _mpl_imported = False
    
    def __init__(self, file = None):
        self.source = file
        self.sink = None
        self.doctype = 'tex'
        self.parsed = None
        self.executed = None
        self.formatted = None
        self.isparsed = False
        self.isexecuted = False
        self.isformatted = False
        self.usematplotlib = True
        self.usesho = False
        self.usepygments = False
        self.defaultoptions = dict(echo = True,
                            results = 'verbatim',
                            fig = False,
                            evaluate = True,
                            width = None,
                            caption = False,
                            term = True)
        self.rcParams =  {'figure.figsize' : (6, 4),
                           'savefig.dpi': 100,
                           'font.size' : 10 }
        self.setformat(self.doctype)


    def setformat(self, doctype = 'tex'):
        if doctype == 'tex':
            self.formatdict = dict(codestart = '\\begin{verbatim}', 
                codeend = '\end{verbatim}\n',
                outputstart = '\\begin{verbatim}', 
                outputend = '\end{verbatim}\n', 
                indent = '',
                figfmt = '.pdf',
                extension = 'tex',
                width = '\\textwidth',
                doctype = 'tex')
            self.usepygments = False
        if doctype == 'minted':
                self.formatdict = dict(codestart = '\\begin{minted}{python}', 
                codeend = '\end{minted}\n',
                outputstart = '\\begin{minted}{python}', 
                outputend = '\end{minted}\n', 
                indent = '',
                figfmt = '.pdf',
                extension = 'tex',
                width = '\\textwidth',
                doctype = 'minted')

        if doctype == 'rst':
            self.formatdict = dict(codestart = '::\n', 
                codeend = '\n\n',
                outputstart = '::\n', 
                outputend = '\n\n',
                #rst has specific format (doctest) for term blocks
                termstart = '',
                termend = '\n\n', 
                termindent = '',
                indent = '    ',
                figfmt = '.png',
                extension = 'rst',
                width = '15 cm',
                doctype = 'rst')
        if doctype == 'pandoc':
            self.formatdict = dict(codestart = '~~~~{.python}',
                codeend = '~~~~~~~~~~~~~\n\n',
                outputstart = '~~~~{.python}', 
                outputend = '~~~~~~~~~~~~~\n\n', 
                indent = '',
                termindent = '',
                figfmt = '.png',
                extension = 'md',
                width = '15 cm',
                doctype = 'pandoc')
        if doctype == 'sphinx':
            self.formatdict = dict(codestart = '::\n', 
                codeend = '\n\n',
                outputstart = '.. code-block::\n', 
                outputend = '\n\n',
                #rst has specific format (doctest) for term blocks
                termstart = '',
                termend = '\n\n', 
                termindent = '',
                indent = '    ',
                #Sphinx determines the figure format automatically
                #for different output formats
                figfmt = '.*',
                savedformats = ['.png', '.pdf'],
                extension = 'rst',
                width = '15 cm',
                doctype = 'rst')

        #Fill in the blank options that are now only used for rst
        #but also allow e.g. special latex style for terminal blocks etc.
        self._fillformatdict()

    def _fillformatdict(self):
        """Fill in the blank fields in formatdictionary"""
        self._fillkey('termstart', self.formatdict['codestart'])
        self._fillkey('termindent', self.formatdict['indent'])
        self._fillkey('termend', self.formatdict['codeend'])
        self._fillkey('savedformats', list([self.formatdict['figfmt']]))
    
    def _fillkey(self, key, value):
        if not self.formatdict.has_key(key):
            self.formatdict[key] = value

    def _chunkstotuple(self, code):
        # Make a list of tuples from the list of chuncks
        a = list()
    
        for i in range(len(code)-1):
            x = (code[i], code[i+1])
            a.append(x)
        return(a)

    def _chunkstodict(self, chunk):
        if (re.findall('@(\s|)\n', chunk[0])) and not (re.findall('<<(.|)>>=', chunk[1])):
            return({'type' : 'doc', 'content':chunk[1]})
        if (re.findall('<<(.|)+>>=', chunk[0])):
            codedict = {'type' : 'code', 'content':chunk[1]}
            codedict.update(self._getoptions(chunk[0]))
            return(codedict)       

    def _getoptions(self, opt):
        defaults = self.defaultoptions.copy() 

        # Aliases for False and True to conform with Sweave syntax
        FALSE = False
        TRUE = True

        #Parse options from chunk to a dictionary 
        optstring = re.findall('[^<<]+[^>>=.+]', opt)
        if not optstring:
            return(defaults)
        exec("chunkoptions =  dict(" + optstring[0] + ")")
        #Update the defaults 
        defaults.update(chunkoptions)
        return(defaults)

    def parse(self):
        codefile = open(self.source, 'r')
        #Prepend "@\n" to code in order to
        #ChunksToDict to work with the first text chunk
        code = "@\n" + codefile.read()
        codefile.close()
        #Split file to list at chunk separators
        chunksep = re.compile('(<<(.|)+>>=)|(@(\s|)\n)')
        codelist = chunksep.split(code)
        codelist = filter(lambda x : x != None, codelist)
        codelist = filter(lambda x :  not x.isspace() and x != "", codelist)
        #Make a tuple for parsing
        codetuple = self._chunkstotuple(codelist)
        #Parse code+options and text chunks from the tuple
        parsedlist = map(self._chunkstodict, codetuple)
        parsedlist = filter(lambda x: x != None, parsedlist)
        #number codechunks, start from 1
        n = 1
        for chunk in parsedlist:
            if chunk['type'] == 'code':
                chunk['number'] = n
                n += 1
        self.parsed = parsedlist
        self.isparsed = True

    def loadstring(self, code):
        tmp = StringIO.StringIO()
        stdold = sys.stdout
        sys.stdout = tmp
        exec(code, Pweb.globals) #self.globals)
        result = "\n" + tmp.getvalue()
        tmp.close()
        sys.stdout = stdold
        return(result)

    def loadterm(self, chunk):
        #Write output to a StringIO object
        #loop trough the code lines
        statement = ""
        prompt = ">>>"
        chunkresult = "\n"
        block = chunk.lstrip().splitlines()
   
        for x in block:
            chunkresult += ('%s %s\n' % (prompt, x))
            statement += x + '\n'

            # Is the statement complete?
            compiled_statement = code.compile_command(statement)
            if compiled_statement is None:
                # No, not yet.
                prompt = "..."
                continue

            if prompt != '>>>':
                chunkresult += ('%s \n' % (prompt))

            tmp = StringIO.StringIO()
            stdold = sys.stdout
            sys.stdout = tmp
            return_value = eval(compiled_statement, Pweb.globals)#self.globals)
            result = tmp.getvalue()
            if return_value is not None:
                result += repr(return_value)
            tmp.close()
            sys.stdout = stdold
            if result:
                for line in result.splitlines():
                    chunkresult += line + '\n'

            statement = ""
            prompt = ">>>"

        return(chunkresult)

    def loadinline(self, chunk):
        matches = re.finditer("<[^>]*?py.*?>[^<]*</[^>]*?py.*?>", chunk)
        if not matches:
            return(chunk)
        start = 0
        result = ""
        for match in matches:
            index = match.span()
            before = chunk[start : (index[0])]
            start = index[1]
            #evaluate inline code, wrapped in a print statement
            evaluated = self.loadstring("print(" + re.findall("[^<>]+(?=[<])", match.group(0))[0] + ")" ).rstrip()
            result += before + evaluated

        if (start < len(chunk)):
            result += chunk[start:len(chunk)]
        return(result)      

    def _runcode(self, chunk):

        if chunk['type'] != 'doc' and chunk['type'] !='code':
            return(chunk)
        
        #Make function to dispatch based on the type
        #Execute a function from a list of functions
        #Store builtin functions in a class and add them to a list
        #when the object initialises or just use getattr?
		
		#List functions from a class:
        #filter(lambda x : not x.startswith('_')   ,dir(pweave.PwebFormatters))
		
		#Users can then append their own functions
        #filter(lambda x: x.func_name=='f', a)[0](10)

        if chunk['type'] == 'doc':
            chunk['content'] = self.loadinline(chunk['content'])
            return(chunk)
       
       #Settings for figures, matplotlib and sho 
        if chunk['width'] is None:
                chunk['width'] = self.formatdict['width']
        if self.usematplotlib:
            if not self._mpl_imported:
                import matplotlib
                matplotlib.use('Agg')
                matplotlib.rcParams.update(self.rcParams)
            import matplotlib.pyplot as plt
            import matplotlib
            self._mpl_imported = True
            
            #['figure.figsize'] = (6, 4)
            #matplotlib.rcParams['figure.dpi'] = 200 
        #Sho should be added in users code if it is used
        #if self.usesho:
        #    sys.path.append("C:\Program Files (x86)\Sho 2.0 for .NET 4\Sho")
        #    from sho import *
        if chunk['type'] == 'code':
            sys.stdout.write("Processing chunk " + str(chunk['number']) + '\n')
            #Term always sets echo and eval to true
            if chunk['term']:
                #try to use term, if fail use exec whole chunk
                #term seems to fail on function definitions
                stdold = sys.stdout
                try:
                    chunk['result'] = self.loadterm(chunk['content'])
                except Exception as inst:
                    sys.stdout = stdold
                    sys.stderr.write('Failed to execute chunk in term mode executing with term = False instead\nThis can sometimes happen at least with function definitions even if there is no syntax error\nEXCEPTION :')
                    sys.stderr.write('%s\n%s\n' % (type(inst), inst.args))
                    chunk['result'] = self.loadstring(chunk['content'])
                    chunk['term'] = False
            elif chunk['evaluate'] == True: 
                    chunk['result'] = self.loadstring(chunk['content'])
            else:
                    chunk['result'] = ''
        #After executing the code save the figure
        if chunk['fig']:
                figname = Pweb.figdir + 'Fig' +str(chunk['number']) + self.formatdict['figfmt']
                chunk['figure'] = figname
                if self.usematplotlib:
                    for format in self.formatdict['savedformats']:
                        plt.savefig(Pweb.figdir + 'Fig' + str(chunk['number']) + format)
                        plt.draw()
                    plt.clf()
                if self.usesho:
                    from sho import saveplot
                    saveplot(figname)
        return(chunk)

    def run(self):
        if not self.isparsed:
            self.parse()
        self.executed = map(self._runcode, self.parsed)
        self.isexecuted = True

    def format(self):
        if not self.isexecuted:
            self.run()
        self.formatted = map(self._formatchunks, self.executed)
        self.isformatted = True

    def write(self):
        if not self.isformatted:
            self.format()
        if self.sink is None:
            self.sink = re.split("\.+[a-zA-Z]+$", self.source)[0] + '.' + self.formatdict['extension']
        f = open(self.sink, 'w')
        f.write("".join(self.formatted))
        f.close()
        sys.stdout.write('Pweaved %s to %s\n' % (self.source, self.sink))

    def weave(self):
        self.parse()
        self.run()
        self.format()
        self.write()

    def tangle(self):
        self.parse()
        target = re.split("\.+[a-zA-Z]+$", self.source)[0]
        target = self.source.split('.')[-2] + '.py'
        code = filter(lambda x : x['type'] == 'code', self.parsed)
        code = map(lambda x : x['content'], code)
        f = open(target, 'w')
        f.write('\n'.join(code))
        f.close()
        sys.stdout.write('Tangled code from %s to %s\n' % (self.source, target))

    def _indent(self, text):
        return(text.replace('\n', '\n' + self.formatdict['indent']))

    def _termindent(self, text):
        return(text.replace('\n', '\n' + self.formatdict['termindent']))

    def _getformatter(self, chunk):
        """Call code from pweave.formatters and user provided formatters
        allows overriding default options for doc and code chunks
        the function needs to return a string"""
        #Check if there are custom functions in Pweb.chunkformatter
        f = filter(lambda x: x.func_name==('format%(type)schunk' % chunk), Pweb.chunkformatters)
        if f:
            return(f[0](chunk))
        #Check built-in formatters from pweave.formatters
        if hasattr (formatters, ('format%(type)schunk' % chunk)):
            result = getattr(formatters, ('format%(type)schunk' % chunk))(chunk)
            return(result)
        #If formatter is not found
        if chunk['type'] == 'code' or chunk['type'] == 'doc':
            return(chunk)
        sys.stderr.write('UNKNOWN CHUNK TYPE: %s \n' % chunk['type'])
        return(None)

    def _pygmentize(self, code):
        highlighted = highlight(code, PythonLexer(), LatexFormatter())
        return(highlighted)

    def _formatchunks(self, chunk):     
        codestart = self.formatdict['codestart']
        codeend = self.formatdict['codeend']
        termstart = self.formatdict['termstart']
        termend = self.formatdict['termend']
        outputstart = self.formatdict['outputstart'] 
        outputend = self.formatdict['outputend']
        indent = self.formatdict['indent']
       
        #add formatdict to the same with chunks dictionary, makes formatting 
        #commands more compact and makes options available for custom   
        #formatters
        chunk.update(self.formatdict)
            
        #Call custom formatters
        code = self._getformatter(chunk)
   
        if code is not None and type(code)!=dict:
            return(code)
        if code is None:
            return('UNKNOWN CHUNK TYPE: %s \n' % chunk['type'])

        #Muista poistaa!
        chunk = code

        #A doc chunk
        if chunk['type'] == 'doc':
             return(chunk['content'])
       
        #Code is not executed
        if not chunk['evaluate']:
            if chunk['echo']:
                return(chunk['code'])
            else:
                return('')
        
        #Code is executed
        #-------------------
        result = ""

        #Term sets echo to true
        if chunk['term']:
            if self.usepygments:
                result = self._pygmentize(chunk['content'])
            else:
                chunk['result'] = self._termindent(chunk['result'])
                result = '%(termstart)s%(result)s%(termend)s' % chunk    

        #Other things than term
        elif chunk['evaluate'] and chunk ['echo'] and chunk['results'] == 'verbatim':
            if self.usepygments:
                result = self._pygmentize(chunk['content'])
            else:
                result = codestart + self._indent(chunk['content']) + codeend
                
            if len(chunk['result']) > 1:
                if self.usepygments:
                    result += self._pygmentize(chunk['result'])
                else:
                    chunk['result'] = self._indent(chunk['result'])
                    result += '%(outputstart)s%(result)s%(outputend)s' % chunk
        elif chunk['evaluate'] and chunk ['echo'] and chunk['results'] != 'verbatim':
                result = (codestart + chunk['content'] + codeend +
                         chunk['result'].replace('\n', '', 1))
        elif chunk['evaluate'] and not chunk['echo']:
                #Remove extra line added when results are captured phase
                result = chunk['result'].replace('\n', '', 1)
        else:
            result = "\\large{NOT YET IMPLEMENTED!!\n}" 
            result += str(chunk)
        #Handle figures
        if chunk['fig']:
            #Call figure formatting function
            figstring = getattr(formatters, ('add%sfigure' % self.formatdict['doctype']))(chunk)
            
            result += figstring
        return(result) 
    
if __name__ == "__main__": 
    if sys.platform == 'cli':
        pweave("sho.Rnw")
        os.system("pdflatex sho.tex")
        os.system("start sho.pdf")
    else:
        #pweave("matex.Rnw")
        #os.system("pdflatex matex.tex")
        #os.system('start matex.pdf')
        pweave("ma.pnw", doctype ='sphinx')
        os.system('rst2html.py ma.rst ma.html')
        pweave('ma.mdw', doctype = 'pandoc')
        os.system('pandoc -s ma.md -o map.html')
        #os.system('pdflatex ma.tex')
        #os.system('start ma.pdf')