// ===========================================================================
//
//                            PUBLIC DOMAIN NOTICE
//            National Center for Biotechnology Information (NCBI)
//
//  This software/database is a "United States Government Work" under the
//  terms of the United States Copyright Act. It was written as part of
//  the author's official duties as a United States Government employee and
//  thus cannot be copyrighted. This software/database is freely available
//  to the public for use. The National Library of Medicine and the U.S.
//  Government do not place any restriction on its use or reproduction.
//  We would, however, appreciate having the NCBI and the author cited in
//  any work or product based on this material.
//
//  Although all reasonable efforts have been taken to ensure the accuracy
//  and reliability of the software and data, the NLM and the U.S.
//  Government do not and cannot warrant the performance or results that
//  may be obtained by using this software or data. The NLM and the U.S.
//  Government disclaim all warranties, express or implied, including
//  warranties of performance, merchantability or fitness for any particular
//  purpose.
//
// ===========================================================================
//
// File Name:  index.go
//
// Author:  Jonathan Kans
//
// ==========================================================================

package eutils

import (
	"bufio"
	"cmp"
	"compress/gzip"
	"container/heap"
	"fmt"
	"html"
	"io"
	"maps"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"runtime/debug"
	"slices"
	"strings"
	"sync"
	"sync/atomic"
	"time"
	"unicode"
)

// INDEXED AND INVERTED FILE FORMATS

// Local archive indexing reads original records (such as PubmedArticle XML) and produces IdxDocument records.
// For PubMed and PMC databases, terms in Title and Title/Abstract fields include term positions as XML attributes:

/*

  ...
  <IdxDocument>
    <IdxUid>2539356</IdxUid>
    <IdxSearchFields>
      <UID>0002539356</UID>
      <SIZE>13751</SIZE>
      <YEAR>1989</YEAR>
      <DATE>1989 04</DATE>
      <RDAT>2019 05 08</RDAT>
      <JOUR>J Bacteriol</JOUR>
      <JOUR>2985120R</JOUR>
      <JOUR>0021-9193</JOUR>
      <JOUR>Journal of Bacteriology</JOUR>
      <JOUR>J Bacteriol</JOUR>
      <JOUR>0021-9193</JOUR>
      <VOL>171</VOL>
      <ISS>4</ISS>
      <PAGE>1904</PAGE>
      <LANG>eng</LANG>
      <ANUM>2</ANUM>
      <FAUT>Kans JA</FAUT>
      <LAUT>Casadaban MJ</LAUT>
      <AUTH>Kans JA</AUTH>
      <AUTH>Casadaban MJ</AUTH>
      <TITL pos="7">immunity</TITL>
      <TITL pos="1">nucleotide</TITL>
      <TITL pos="3">required</TITL>
      <TITL pos="2">sequences</TITL>
      <TITL pos="5">tn3</TITL>
      <TITL pos="6">transposition</TITL>
      <TIAB pos="145">38</TIAB>
      <TIAB pos="126">acting</TIAB>
      <TIAB pos="188">additional</TIAB>
      <TIAB pos="146">base</TIAB>
      <TIAB pos="125">cis</TIAB>
      <TIAB pos="172,178,187">conferred</TIAB>
      ...
      <PAIR>nucleotide sequences</PAIR>
      <PAIR>sequences required</PAIR>
      <PAIR>tn3 transposition</PAIR>
      <PAIR>transposition immunity</PAIR>
      <PTYP>Journal Article</PTYP>
      <PTYP>Research Support, U.S. Gov&#39;t, P.H.S.</PTYP>
      <DOI>9891 4191 4091 4 171 bj 8211 01</DOI>
      <PMCID>209839</PMCID>
      <PROP>Published In Print</PROP>
      <PROP>Has Abstract</PROP>
      <CODE>d001483</CODE>
      <CODE>d002874</CODE>
      ...
      <MESH>Plasmids</MESH>
      <MESH>Recombination, Genetic</MESH>
      <SUBS>DNA Transposable Elements</SUBS>
      <SUBS>DNA, Bacterial</SUBS>
    </IdxSearchFields>
  </IdxDocument>
  ...

*/

// Inversion reads a set of indexed documents and generates InvDocument records:

/*

  ...
  <InvDocument>
    <InvKey>transposition</InvKey>
    <InvFld>TIAB</InvFld>
    <InvTag>tra</InvTag>
    <TIAB pos="6,122">2539356</TIAB>
  </InvDocument>
  <InvDocument>
    <InvKey>transposition</InvKey>
    <InvFld>TITL</InvFld>
    <InvTag>tra</InvTag>
    <TITL pos="6">2539356</TITL>
  </InvDocument>
  <InvDocument>
    <InvKey>transposition immunity</InvKey>
    <InvFld>PAIR</InvFld>
    <InvTag>tra</InvTag>
    <PAIR>2539356</PAIR>
  </InvDocument>
  ...

*/

// In a local archive, separate ranges of record unique identifiers (UIDs) are indexed and
// inverted as groups, which allows incremental updating. For efficient merging of these
// subsets, and in order to produce term lists and postings files, inverted records should
// be sorted first by term prefix, or tag.

// Tag lengths may be increased from the default 3 characters by a look-up table of two-letter
// prefixes. This is done to simultaneously avoid large numbers of small files (an unnecessary
// burden on the file system) and huge single files (a burden on query resolution).

// However, to accommodate huge databases (such as almost a half billion RefSeq proteins),
// specific fields such as peptide pentamers (PENT), accession (ACCN) and identifier (UID),
// are forced to prefix length 4.

// The two methods for computing prefix length can cause conflicts in the initial inverted set,
// which is sorted by full term (InvKey). A subsequent resorting first by tag (InvTag) and then,
// (for identical tags) by InvKey, and finally by field (InvFld, which also makes a separate
// InvDocument), can resolve out-of-order initial records, such as:

// <InvDocument>
//   <InvKey>glyaa</InvKey>
//   <InvFld>PENT</InvFld>
//   <InvTag>glya</InvTag>
//   <PENT>354004494</PENT>

// coming before:

// <InvDocument>
//   <InvKey>glycoside hydrolase family 1 protein</InvKey>
//   <InvFld>PROD</InvFld>
//   <InvTag>gly</InvTag>
//   <PROD>354002706</PROD>

// Separate inverted index files are merged and used to produce term lists and postings file.
// These can then be searched by passing arguments to EDirect's "xsearch" script.

// ENTREZ2INDEX COMMAND GENERATOR

// MakeE2Commands reads command lines that have been run through xargs for use by Entrez indexing.
func MakeE2Commands(tform, idxargs string) []string {

	var acc []string

	// idxargs file contains one command or argument per line
	if idxargs == "" {
		return acc
	}

	inFile, err := os.Open(idxargs)
	if err != nil {
		DisplayError("Unable to open index argument array file: %s\n", err.Error())
		return acc
	}
	defer inFile.Close()

	scanr := bufio.NewScanner(inFile)
	if scanr == nil {
		DisplayError("Unable to create NewScanner")
		return acc
	}

	for scanr.Scan() {

		line := scanr.Text()

		// do NOT skip empty line or trim spaces, in order to allow "" or " " arguments

		acc = append(acc, line)
	}

	return acc
}

// UPDATE CACHED INVERTED-INDEX FILES FROM LOCAL ARCHIVE FOLDERS

// e2IndexConsumer callbacks have access to application-specific data as closures
type e2IndexConsumer func(inp <-chan XMLRecord) <-chan XMLRecord

// EntrezIndex uses a specific xtract expression to convert custom records into IdxDocument XML
func EntrezIndex(recname string, csmr e2IndexConsumer, in io.Reader) <-chan string {

	if in == nil {
		return nil
	}

	if recname == "" || csmr == nil {
		return nil
	}

	out := make(chan string, chanDepth)
	if out == nil {
		DisplayError("Unable to create indexer channel")
		return nil
	}

	re := regexp.MustCompile(">[ \n\r\t]*<")
	if re == nil {
		DisplayError("Unable to create regular expression")
		return nil
	}

	go func(recname string, csmr e2IndexConsumer, in io.Reader) {

		defer close(out)

		// use full XML parser to ensure recursive records are handled properly
		rdr := CreateXMLStreamer(in, nil)

		xmlq := CreateXMLProducer(recname, "", false, rdr)

		// callback passes cmds and transform values as closures to xtract createConsumers
		tblq := csmr(xmlq)

		for curr := range tblq {

			str := curr.Text

			if str == "" {
				continue
			}

			// clean up white space between stop tag and next start tag, replacing with a single newline
			str = re.ReplaceAllString(str, ">\n<")

			// ensure that XML string ends with a right angle bracket, a convention expected by xml.go functions
			idx := strings.LastIndex(str, ">")
			if idx >= 0 {
				idx++
				str = str[:idx]
			}

			out <- str
		}
	}(recname, csmr, in)

	return out
}

// EntrezInvert converts a set of IdxDocument XML records into an InvDocument XML record
func EntrezInvert(in io.Reader) <-chan string {

	if in == nil {
		return nil
	}

	out := make(chan string, chanDepth)
	if out == nil {
		DisplayError("Unable to create inverter channel")
		return nil
	}

	go func(in io.Reader) {

		defer close(out)

		// can use simpler text parser for reading (non-recursive) IdxDocument XML
		rdr := CreateTextStreamer(in)

		txtq := CreateTextProducer("<IdxDocument>", "", "", 0, 0, rdr)

		iifq := InvertIndexedFile(nil, txtq)

		for str := range iifq {
			out <- str
		}
	}(in)

	return out
}

// IndexAndInvertArchive explores archive files and incrementally updates inverted index files.
func IndexAndInvertArchive(db, recname string, csmr e2IndexConsumer) <-chan string {

	if db == "" {
		return nil
	}

	if csmr == nil {
		return nil
	}

	// obtain paths from environment variable(s)
	pths := ResolveArchivePaths(db)
	if pths == nil {
		DisplayError("Unable to get local archive configuration paths")
		os.Exit(1)
	}

	openAndConfirmMount := func(folder, name string) string {

		base, ok := pths.GetLocalPath(folder)

		if base == "" {
			DisplayError("Unable to get local %s path", name)
			os.Exit(1)
		}
		if !ok {
			DisplayError("Local %s path is not mounted", base)
			os.Exit(1)
		}

		return base
	}

	archiveBase := openAndConfirmMount("Archive", "archive")

	invertBase := openAndConfirmMount("Invert", "invert")

	temporaryBase := openAndConfirmMount("Temporary", "temporary")

	re := regexp.MustCompile(">[ \n\r\t]*<")
	if re == nil {
		return nil
	}

	var progressTime time.Time
	var progressDots atomic.Uint32

	listLeafFolders := func(path string) <-chan string {

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create archive explorer channel")
			os.Exit(1)
		}

		isTwoDigits := func(str string) bool {

			if len(str) != 2 {
				return false
			}

			ch := str[0]
			if ch < '0' || ch > '9' {
				return false
			}

			ch = str[1]
			if ch < '0' || ch > '9' {
				return false
			}

			return true
		}

		getSubFolderNames := func(path string) []string {

			dir := filepath.Join(archiveBase, path)

			contents, err := os.ReadDir(dir)
			if err != nil {
				return nil
			}

			dirs := make([]string, 0, 100)
			if dirs == nil {
				return nil
			}

			for _, item := range contents {
				if !item.IsDir() {
					continue
				}
				name := item.Name()
				if name == "" || !isTwoDigits(name) {
					continue
				}
				dirs = append(dirs, name)
			}

			if len(dirs) > 1 {
				// ensure folder names are sorted from 00 to 99
				slices.SortFunc(dirs, CompareNumericStringKeys)
			}

			return dirs
		}

		// recursive definition
		var visitSubFolders func(path, name string, out chan<- string)

		// visitSubFolders recursively visits the local archive directory hierarchy to leaf directories
		visitSubFolders = func(path, name string, out chan<- string) {

			// find subdirectories of current folder
			dirs := getSubFolderNames(path)

			if dirs == nil || len(dirs) < 1 {

				// if no further subdirectories, report path to data files
				out <- path

				return
			}

			// otherwise continue descending another level
			for _, dr := range dirs {
				// skip Sentinels folder (on top level)
				if len(dr) != 2 || !IsAllDigits(dr) {
					continue
				}

				sub := filepath.Join(path, dr)
				nm := name + dr
				// recursively explore subdirectories
				visitSubFolders(sub, nm, out)
			}
		}

		go func(path string, out chan<- string) {

			defer close(out)

			visitSubFolders(path, "", out)
		}(path, out)

		return out
	}

	listUnindexedFiles := func(leaf string) <-chan string {

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create unindexed explorer channel")
			os.Exit(1)
		}

		// return a map of relative paths to allow quick detection of missing inverted index files
		visitLeafFiles := func(base, path, suffix string) map[string]bool {

			if base == "" || suffix == "" {
				return nil
			}

			dir := filepath.Join(base, path)

			contents, err := os.ReadDir(dir)
			if err != nil {
				return nil
			}

			fils := make(map[string]bool)

			for _, item := range contents {
				if item.IsDir() {
					continue
				}
				name := item.Name()
				if name == "" {
					continue
				}

				// for quick testing, uncomment the next command to only index 1/10 of archived files
				// if strings.HasSuffix(name, ".archive") && len(name) == 14 && name[5] != '0' { continue }

				if before, ok0 := strings.CutSuffix(name, suffix); ok0 {
					name = before
					fils[name] = true
				}
			}

			return fils
		}

		go func(leaf string, out chan<- string) {

			defer close(out)

			rcvs := visitLeafFiles(archiveBase, leaf, ".archive")
			if rcvs == nil {
				return
			}

			missing := make([]string, 0, 100)
			if missing == nil {
				return
			}

			keys := slices.SortedFunc(maps.Keys(rcvs), CompareNumericStringKeys)

			// look for equivalent files in invert directory
			idxs := visitLeafFiles(invertBase, leaf, ".inv.gz")

			for _, arch := range keys {

				// skip existing index files
				if idxs != nil && len(idxs) > 0 && idxs[arch] {
					continue
				}

				// missing files are either for new archive files or were deleted as stale by the last archive update
				missing = append(missing, arch)
			}

			if len(missing) < 1 {
				return
			}
			slices.Sort(missing)

			for _, arch := range missing {
				// process one archive leaf folder at a time
				out <- arch
			}

		}(leaf, out)

		return out
	}

	saveToFile := func(base, path, file, suffix string, compress bool, inp <-chan string) <-chan string {

		if inp == nil {
			return nil
		}

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create saveToFile channel")
			os.Exit(1)
		}

		go func(base, path, file, suffix string, inp <-chan string, out chan<- string) {

			defer close(out)

			var (
				wrtr *bufio.Writer
				zpr  *gzip.Writer
				err  error
			)

			dpath := filepath.Join(base, path)
			if dpath == "" {
				return
			}

			err = os.MkdirAll(dpath, os.ModePerm)
			if err != nil {
				fmt.Fprintf(os.Stderr, "%s\n", err.Error())
				return
			}
			fpath := filepath.Join(dpath, file+suffix)
			if fpath == "" {
				return
			}

			// overwrites and truncates existing file
			fl, err := os.Create(fpath)
			if err != nil {
				fmt.Fprintf(os.Stderr, "%s\n", err.Error())
				return
			}

			if compress {
				zpr, err = gzip.NewWriterLevel(fl, gzip.BestSpeed)
				if err != nil {
					DisplayError("Unable to create compressor")
					os.Exit(1)
				}
				wrtr = bufio.NewWriter(zpr)
			} else {
				wrtr = bufio.NewWriter(fl)
			}

			// write contents
			last := ""

			for str := range inp {
				if str == "" {
					continue
				}
				wrtr.WriteString(str)
				last = str
			}

			if !strings.HasSuffix(last, "\n") {
				wrtr.WriteString("\n")
			}

			err = wrtr.Flush()
			if err != nil {
				fmt.Fprintf(os.Stderr, "%s\n", err.Error())
				return
			}

			if compress {
				err = zpr.Close()
				if err != nil {
					fmt.Fprintf(os.Stderr, "%s\n", err.Error())
					return
				}
			}

			// fl.Sync()

			err = fl.Close()
			if err != nil {
				fmt.Fprintf(os.Stderr, "%s\n", err.Error())
				return
			}

			// print progress dots for one leaf folder on the same line
			fmt.Fprintf(os.Stderr, ".")
			progressDots.Add(1)

			out <- file
		}(base, path, file, suffix, inp, out)

		return out
	}

	printElapsedSeconds := func(sttTime time.Time, dots uint32, indent bool) {

		const oneHundredSeconds = "                                                                                                    "

		stpTime := time.Now()
		duration := stpTime.Sub(sttTime)
		seconds := float64(duration.Nanoseconds()) / 1e9

		// calculate leading spaces so seconds values line up even on lines
		padding := ""
		padLen := 100 - dots
		if padLen > 0 && padLen <= 100 {
			padding = oneHundredSeconds[:padLen]
		}

		if indent {
			fmt.Fprintf(os.Stderr, "%s %5.*f\n      ", padding, 1, seconds)
		} else {
			fmt.Fprintf(os.Stderr, "%s %5.*f\n", padding, 1, seconds)
		}
	}

	indexArchiveFiles := func(leaf string, inp <-chan string) <-chan string {

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create indexer channel")
			os.Exit(1)
		}

		var count atomic.Uint32

		cleanIndexFilesEx := func(inp <-chan XMLRecord) <-chan string {

			if inp == nil {
				DisplayError("No input to index cleaner")
				os.Exit(1)
			}

			out := make(chan string, chanDepth)
			if out == nil {
				DisplayError("Unable to create index cleaner channel")
				os.Exit(1)
			}

			cleaner := func(wg *sync.WaitGroup, inp <-chan XMLRecord, out chan<- string) {

				defer wg.Done()

				for curr := range inp {

					str := curr.Text

					if str == "" {
						continue
					}

					// clean up white space between stop tag and next start tag, replacing with a single newline
					str = re.ReplaceAllString(str, ">\n<")

					// ensure that XML string ends with a right angle bracket, a convention expected by xml.go functions
					idx := strings.LastIndex(str, ">")
					if idx >= 0 {
						idx++
						str = str[:idx]
					}

					out <- str[:]
				}
			}

			var wg sync.WaitGroup

			for range numProcs {
				wg.Add(1)
				go cleaner(&wg, inp, out)
			}

			go func() {
				wg.Wait()
				close(out)
			}()

			return out
		}

		indexer := func(wg *sync.WaitGroup, leaf string, inp <-chan string, out chan<- string) {

			defer wg.Done()

			for arch := range inp {

				dpath := filepath.Join(archiveBase, leaf)
				fpath := filepath.Join(dpath, arch+".archive")

				fl, err := os.Open(fpath)
				if err != nil {
					DisplayError("Unable to open file '%s' for collection", fpath)
					continue
				}
				defer fl.Close()

				sacq := StreamArchiveComponents(fl)

				// use full XML parser to ensure recursive records are handled properly
				rdr := CreateXMLStreamer(nil, sacq)
				xmlq := CreateXMLProducer(recname, "", false, rdr)

				// callback passes cmds and transform values as closures to xtract createConsumers
				tblq := csmr(xmlq)

				// simple cleanup of XML formatting
				cifq := cleanIndexFilesEx(tblq)

				stfq := saveToFile(temporaryBase, "", arch, ".e2x", false, cifq)

				for fl := range stfq {
					out <- fl
				}

				// force periodic garbage collection to prevent memory pressure
				count.Add(1)
				if count.Load() > 5 {
					count.Store(0)
					runtime.GC()
					debug.FreeOSMemory()
				}
			}
		}

		var wg sync.WaitGroup

		for range numProcs {
			wg.Add(1)
			go indexer(&wg, leaf, inp, out)
		}

		go func() {
			wg.Wait()
			close(out)
		}()

		return out
	}

	invertArchiveFiles := func(leaf string, inp <-chan string) <-chan string {

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create inverter channel")
			os.Exit(1)
		}

		var count atomic.Uint32

		inverter := func(wg *sync.WaitGroup, leaf string, inp <-chan string, out chan<- string) {

			defer wg.Done()

			for arch := range inp {

				fpath := filepath.Join(temporaryBase, arch+".e2x")

				f, err := os.Open(fpath)
				if err != nil {
					DisplayError("Unable to open file '%s' for inversion", fpath)
					continue
				}
				defer f.Close()

				// can use simpler text parser for non-recursive IdxDocument XML start tag
				rdr := CreateTextStreamer(f)
				txtq := CreateTextProducer("<IdxDocument>", "", "", 0, 0, rdr)

				iifq := InvertIndexedFile(nil, txtq)

				// compress result and save in proper leaf within Invert folder
				stfq := saveToFile(invertBase, leaf, arch, ".inv.gz", true, iifq)

				for fl := range stfq {
					out <- fl
				}

				// force periodic garbage collection to prevent memory pressure
				count.Add(1)
				if count.Load() > 5 {
					count.Store(0)
					runtime.GC()
					debug.FreeOSMemory()
				}
			}
		}

		var wg sync.WaitGroup

		// launching several inverters (using numProcs instead of numServe)
		// keeps CPUs active but avoids causing system memory pressure
		for range numProcs {
			wg.Add(1)
			go inverter(&wg, leaf, inp, out)
		}

		go func() {
			wg.Wait()
			close(out)
		}()

		return out
	}

	processLeafFolders := func(inp <-chan string) <-chan string {

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create leaf explorer channel")
			os.Exit(1)
		}

		go func(inp <-chan string, out chan<- string) {

			defer close(out)

			channelSorter := func(inp <-chan string) <-chan string {

				if inp == nil {
					return nil
				}

				var values []string

				const chanSortBufSize = 8

				out := make(chan string, chanSortBufSize)
				if out == nil {
					return nil
				}

				go func(inp <-chan string, out chan<- string) {

					defer close(out)

					for str := range inp {
						values = append(values, str)
					}

					printElapsedSeconds(progressTime, progressDots.Load(), true)

					progressTime = time.Now()
					progressDots.Store(0)

					if len(values) < 1 {
						return
					}
					slices.Sort(values)

					for _, str := range values {
						out <- str
					}
				}(inp, out)

				return out
			}

			doSingleLeaf := func(leaf string) {

				progressTime = time.Now()
				progressDots.Store(0)

				arcq := listUnindexedFiles(leaf)

				ixfq := indexArchiveFiles(leaf, arcq)
				ixsq := channelSorter(ixfq)

				ivfq := invertArchiveFiles(leaf, ixsq)
				ivsq := channelSorter(ivfq)

				// uncomment return statement to leave intermediate files for testing
				// return

				for arch := range ivsq {
					fpath := filepath.Join(temporaryBase, arch+".e2x")
					err := os.Remove(fpath)
					if err != nil {
						fmt.Fprintf(os.Stderr, "Unable to remove %s: %s\n", fpath, err.Error())
					}
				}

				runtime.GC()
				runtime.Gosched()
				debug.FreeOSMemory()
			}

			for leaf := range inp {

				// print current archive leaf directory (e.g., "00/02 ")
				fmt.Fprintf(os.Stderr, "%s ", leaf)

				doSingleLeaf(leaf)

				fmt.Fprintf(os.Stderr, "\n")

				out <- leaf

				// uncomment break statement to only process one folder for testing
				// break
			}
		}(inp, out)

		return out
	}

	llfq := listLeafFolders("")
	iilq := processLeafFolders(llfq)

	if llfq == nil || iilq == nil {
		DisplayError("Unable to process leaf folders")
		os.Exit(1)
	}

	return iilq
}

// INDEX INVERSION FUNCTION

type Invert struct {
	Tag   string
	Term  string
	Field string
	UID   string
	Attrs string
}

// InvertHeap methods satisfy heap.Interface
type InvertHeap []Invert

func (h InvertHeap) Len() int {
	return len(h)
}

func (h InvertHeap) Less(i, j int) bool {

	// 2 to 4 letter term prefix is used for sequential merging of inverted index files
	// from an entire database prior to final creation of term lists and postings tables
	res := cmp.Compare(h[i].Tag, h[j].Tag)
	if res < 0 {
		return true
	}
	if res > 0 {
		return false
	}

	res = cmp.Compare(h[i].Term, h[j].Term)
	if res < 0 {
		return true
	}
	if res > 0 {
		return false
	}

	res = cmp.Compare(h[i].Field, h[j].Field)
	if res < 0 {
		return true
	}
	if res > 0 {
		return false
	}

	res = CompareNumericStringKeys(h[i].UID, h[j].UID)
	if res < 0 {
		return true
	}
	if res > 0 {
		return false
	}

	return i < j
}

func (h InvertHeap) Swap(i, j int) {
	h[i], h[j] = h[j], h[i]
}

// Push works on pointer to InvertHeap
func (h *InvertHeap) Push(x any) {
	*h = append(*h, x.(Invert))
}

// Pop works on pointer to InvertHeap
func (h *InvertHeap) Pop() any {
	old := *h
	n := len(old)
	x := old[n-1]
	*h = old[0 : n-1]
	return x
}

// InvertIndexedFile reads IdxDocument XML records and writes InvDocument XML records
func InvertIndexedFile(inps <-chan string, inpt <-chan TextRecord) <-chan string {

	if inps == nil && inpt == nil {
		return nil
	}

	if inps != nil && inpt != nil {
		DisplayError("Multiple input arguments to InvertIndexedFile")
		return nil
	}

	indexDispenser := func(inps <-chan string, inpt <-chan TextRecord) <-chan Invert {

		if inps == nil && inpt == nil {
			return nil
		}

		out := make(chan Invert, chanDepth)
		if out == nil {
			DisplayError("Unable to create dispenser channel")
			os.Exit(1)
		}

		go func(inps <-chan string, inpt <-chan TextRecord, out chan<- Invert) {

			defer close(out)

			currUID := ""

			doDispense := func(fld, pos, term string) {

				if fld == "IdxUid" {
					currUID = term
					return
				}

				term = html.UnescapeString(term)

				// expand Greek letters, anglicize characters in other alphabets
				if IsNotASCII(term) {
					term = TransformAccents(term, true, true)
					if HasAdjacentSpacesOrNewline(term) {
						term = CompressRunsOfSpaces(term)
					}
					term = UnicodeToASCII(term)
					if HasFlankingSpace(term) {
						term = strings.TrimSpace(term)
					}
				}

				term = strings.ToLower(term)

				// remove punctuation from term
				term = strings.Map(func(c rune) rune {
					if !unicode.IsLetter(c) && !unicode.IsDigit(c) && c != ' ' && c != '-' && c != '_' {
						return -1
					}
					return c
				}, term)

				term = strings.Replace(term, "_", " ", -1)
				term = strings.Replace(term, "-", " ", -1)

				if HasAdjacentSpacesOrNewline(term) {
					term = CompressRunsOfSpaces(term)
				}
				if HasFlankingSpace(term) {
					term = strings.TrimSpace(term)
				}

				if term == "" || currUID == "" {
					return
				}

				tag := IdentifierKey(term, fld)
				// underscore is only for file name, revert to space for proper alphabetical sorting
				tag = strings.Replace(tag, "_", " ", -1)
				// do NOT call TrimSpace - internal or trailing spaces will be replaced by underscore
				// only when tag is used for file and directory names
				tag = strings.TrimLeft(tag, " ")

				out <- Invert{Tag: tag, Term: term, Field: fld, UID: currUID, Attrs: pos}
			}

			// read partitioned IdxDocument XML records
			if inps != nil {
				for str := range inps {
					StreamValues(str[:], "IdxDocument", doDispense)
				}
			} else if inpt != nil {
				for curr := range inpt {
					str := curr.Text
					StreamValues(str[:], "IdxDocument", doDispense)
				}
			}
		}(inps, inpt, out)

		return out
	}

	indexInverter := func(inp <-chan Invert) <-chan Invert {

		if inp == nil {
			return nil
		}

		out := make(chan Invert, chanDepth)
		if out == nil {
			DisplayError("Unable to create inverter channel")
			os.Exit(1)
		}

		go func(inp <-chan Invert, out chan<- Invert) {

			defer close(out)

			// initialize empty heap
			hp := &InvertHeap{}
			heap.Init(hp)

			// read all objects into heap
			for curr := range inp {
				heap.Push(hp, curr)
			}

			prevTag, prevTerm, prevField, prevUID := "", "", "", ""

			for hp.Len() > 0 {

				// sort by removing lowest item from heap
				curr := heap.Pop(hp).(Invert)

				// fmt.Fprintf(os.Stderr, "%s\t%s\t%s\t%s\t%s\t\n", curr.Tag, curr.Field, curr.UID, curr.Term, curr.Attrs)

				// remove duplicate entries
				if curr.Tag == prevTag && curr.Term == prevTerm && curr.Field == prevField && curr.UID == prevUID {
					continue
				}

				// write to output channel in sorted order
				out <- curr

				// remember last index line
				prevTag, prevTerm, prevField, prevUID = curr.Tag, curr.Term, curr.Field, curr.UID
			}
		}(inp, out)

		return out
	}

	indexResolver := func(inp <-chan Invert) <-chan string {

		if inp == nil {
			return nil
		}

		out := make(chan string, chanDepth)
		if out == nil {
			DisplayError("Unable to create resolver channel")
			os.Exit(1)
		}

		go func(inp <-chan Invert, out chan<- string) {

			defer close(out)

			var buffer strings.Builder

			prevTag, prevTerm, prevField := "", "", ""

			finishRecord := func() {
				// finish old record
				buffer.WriteString("</InvDocument>\n")
				str := buffer.String()
				buffer.Reset()
				// send to output
				out <- str
			}

			for curr := range inp {

				// fmt.Fprintf(os.Stderr, "%s\t%s\t%s\t%s\t%s\t\n", curr.Tag, curr.Field, curr.UID, curr.Term, curr.Attrs)

				if prevTag != "" && buffer.Len() > 0 {
					// NOT comparing curr.UID != prevUID allows fusing of individual records with same tag, term, and field
					if curr.Tag != prevTag || curr.Term != prevTerm || curr.Field != prevField {
						finishRecord()
					}
				}

				if buffer.Len() == 0 {
					// if start of new record, write header
					buffer.WriteString("<InvDocument>\n  <InvKey>")
					buffer.WriteString(curr.Term)
					buffer.WriteString("</InvKey>\n  <InvFld>")
					buffer.WriteString(curr.Field)
					buffer.WriteString("</InvFld>\n  <InvTag>")
					buffer.WriteString(curr.Tag)
					buffer.WriteString("</InvTag>\n")
				}

				// write one index item
				buffer.WriteString("  <")
				buffer.WriteString(curr.Field)
				if curr.Attrs != "" {
					buffer.WriteString(" ")
					buffer.WriteString(curr.Attrs)
				}
				buffer.WriteString(">")
				buffer.WriteString(curr.UID)
				buffer.WriteString("</")
				buffer.WriteString(curr.Field)
				buffer.WriteString(">\n")

				prevTag, prevTerm, prevField = curr.Tag, curr.Term, curr.Field
			}

			if prevTag != "" && buffer.Len() > 0 {
				finishRecord()
			}
		}(inp, out)

		return out
	}

	idsq := indexDispenser(inps, inpt)
	invq := indexInverter(idsq)
	idrq := indexResolver(invq)

	if idsq == nil || invq == nil || idrq == nil {
		return nil
	}

	return idrq
}
