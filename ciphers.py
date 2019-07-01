#/usr/bin/python
import os, sqlite3, csv, re, argparse, uuid, traceback, sys, datetime, glob, time

######################################################################
#
# TODO
# 8-14-2017
#	[ ] - Make it so that you can use -sV without screwing
#			everything up
#	[ ] - Make it possible to specify ports
#
# 8-9-2017
#	[x] - Make the --ips and --nmap flags mutually exclusive
#
# 8-6-2017	
#	[x] - Remove the first line of the nmap output because it contains
#			the phrase ssl-enum-ciphers


######################################################################
#
# Changelog
#
# 5-13-2019
#			- We now report all CBC ciphers on TLS 1.0,1.1 and 1.2
#				in accordance with guidance from qualys regarding
#				the new golden doodle attacks
#
# 8-8-2018
#			- Instead of listing the ciphers explicitly for SSL/TLS1.0
#				we now just print "All" since the whole protocol
#				should be disabled there is no need to be that verbose
#
# 7-13-2018
#			- Because TLSv1.0 is now deprecated we are reporting ALL
#				TLSv1.0 ciphers, just like for SSLv2/3 
#
# 5-16-2018
#			- added a boat load of comments and cleaned up the code
#			- added --deletedb flag to make deleting the sqlite
#				database optional
#			- added code to print out the affected systems for
#				easy pasting into rmaker
#
#
# 3-13-2018
#			- fixed bug for the new ip matching where if 
#				hostnames are not passed in then there are
#				no parenthesis in the output and so we need
#				to still look for an ip the old way
#
# 3-8-2018
#			-Added the \( and \) to the ip address finding
#				regular expression so that rDNS does not
#				end up matching. The real IP is always in
#				parentheses at the end of the line
#				
# 8-12-2017
#			-Added code to skip the first line when reading ciphers
#				file, see TODO 8-6-17
#			-Made the --ips and --nmap arguments mutually exclusive
#			-Changed default outputfile name to include timestamp
#			-Added code to list ALL ciphers if the cipher type is
#				SSLv2/SSLv3 instead of just the non 'A' grade ciphers
#
# 8-9-2017
#			-Removed -sV from the nmap command, makes big problems
#
# 8-8-2017
#			-Added --noping argument
#			-Added -sV to the nmap command
#
# 8-6-2017	
#			-Added s = re.sub("\n*PORT", "PORT", s) to get rid of 
#				extra spaces produced when using older versions 
#				of nmap
#
# 6-31-2017 
#			-Added support for passing multiple input files
#			-Added "DISTINCT" keyword to final sql query
#				to remove any duplicate rows generated by
#				parsing multiple files
#			-Made it so you can just pass list of IPs and
#				the nmap scan will automatically run
#			-Made it so if a list of IPs is passed it, it
#				will automatically get uniq'd	
#
# 6-1-2017	
#			-Added colors
#			-Added checks that the input files being passed in
#				are valid
#
#

# https://stackoverflow.com/questions/287871/print-in-terminal-with-colors-using-python
redText 	= '\033[91m'
greenText 	= '\033[92m'
blueText 	= '\033[94m'

def getCiphers(cipherType, ciphers):
	"""get vulnerable ciphers from ssl-enum-ciphers script"""
	# when "cipherType" is "TLSv1.0"
	# the "ciphers" variable will match the lines with hash marks:
	cipherType = re.escape(cipherType)
	ciphers = re.search("{0}:.*?compressor".format(cipherType), ciphers, re.DOTALL)
	"""
		Nmap scan report for 10.18.38.10
		Host is up (0.0012s latency).
		Not shown: 998 filtered ports
		PORT    STATE SERVICE
		22/tcp  open  ssh  
		443/tcp open  https
		| ssl-enum-ciphers: 
	#	|   TLSv1.0: 
	#	|     ciphers: 
	###	|       TLS_DHE_RSA_WITH_AES_128_CBC_SHA (dh 1024) - A
	###	|       TLS_DHE_RSA_WITH_AES_256_CBC_SHA (dh 1024) - A
	###	|       TLS_RSA_WITH_AES_128_CBC_SHA (rsa 1024) - A
	###	|       TLS_RSA_WITH_AES_256_CBC_SHA (rsa 1024) - A
	##	|       TLS_RSA_WITH_3DES_EDE_CBC_SHA (rsa 1024) - D
	#	|     compressors: 
		|       NULL
		|     cipher preference: server
		|     warnings: 
		|       64-bit block cipher 3DES vulnerable to SWEET32 attack
		|       Weak certificate signature: SHA1 
		|_  least strength: D
		MAC Address: 44:D3:CA:FD:7F:EC (Cisco Systems)
	"""

	try: 
		# check if there were any matches
		ciphers = ciphers.group(0)
	except: 
		# if there were no matches just return
		return ""
	cipherLines = ""

	# this will match the line with two hash marks in the multiline comment above
	# [CA 5-13-2019 changing the regex to match all CBC in accordance with goldendoodle]
	#regexSearchString = "(([A-Z0-9_]).*( [B-Z]))"
	regexSearchString = "(([A-Z].* [B-Z])|([A-Z].*CBC.*[A-Z]))"

	# if the cipher type is SSLv2/SSLv3/TLSv1.0 then we should list all the ciphers,
	# not the just ones less than grade A

	if (("SSL" in cipherType) or ("TLSv1\.0" in cipherType)):
		# this will match all the lines with two OR three hash marks above
		"""getting rid of the line commented out below, if it's SSL/TLS1.0 we can just say "All"
		since the whole protocol needs to be disabled
		8-8-18"""
		# regexSearchString = "(([A-Z0-9_]).*( [A-Z]))"
		cipherLines = "All"
		return cipherLines
	for ciphers in re.findall(regexSearchString, ciphers):
		# ciphers[0] is: TLS_RSA_WITH_AES_256_CBC_SHA (rsa 1024) - A
		# ciphers[0].split(" ")[0] is: TLS_RSA_WITH_AES_256_CBC_SHA
		cipherLines += ciphers[0].split(" ")[0] + "\n"

	# the value returned based on the sample above would simply be
	# TLS_RSA_WITH_3DES_EDE_CBC_SHA
	return cipherLines.rstrip()

def getCiphersSSLv2(ciphers): 
	"""get vulnerable ciphers for output from sslv2 nmap script only"""
	
	"""
	Example "ciphers" to be passed in
		sslv2: 
		|   SSLv2 supported
		|   ciphers: 
	#	|     SSL2_RC4_128_WITH_MD5
	#	|_    SSL2_DES_192_EDE3_CBC_WITH_MD5
	"""

	# this will match the lines with hash marks in the example above
	ciphers = re.findall("[\w]+_[\w]+", ciphers)
	
	# check if there were any matches
	try: 
		cipherLines = ""
		for cipher in ciphers:
			# we want to get all the vulnerable ciphers into one string
			# with a newline between each cipher
			"""getting rid of this, if it's SSL/TLS1.0 we can just say "All"
			since the whole protocol needs to be disabled
			8-8-18"""
			return "All"
			# cipherLines += cipher + "\n"
				
		# return cipherLines.rstrip()

	# if nothing was found return empty string
	except:
		return ""

def nmap(ipListFile, noping):
	ts = time.time()
	outputFile = "{0}.ciphers".format(datetime.datetime.fromtimestamp(ts).strftime('%m-%d-%Y-%H-%M-%S'))
	if (noping == True):
		os.system("nmap -Pn -iL {0} --script sslv2,ssl-enum-ciphers -oN {1}".format(ipListFile, outputFile))
	else:
		os.system("nmap -iL {0} --script sslv2,ssl-enum-ciphers -oN {1}".format(ipListFile, outputFile))

def parseResults(inputFileList, outputFile, deleteDb=True):
	"""given a list of ".ciphers" files, grab all the vulnerable ciphers per 
	host and add them to a database then print out the results
	"""
	# may need to add TLSv1.3 in here one day :X
	cipherTypes = ("SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1", "TLSv1.2")

	# give the db file a unique name
	db = "/tmp/{0}.db".format(uuid.uuid4())	

	# create / connect to database
	conn = sqlite3.connect(db)

	# thanks, https://docs.python.org/3/library/sqlite3.html
	c = conn.cursor()

	# create the table to store our results
	c.execute('''CREATE TABLE IF NOT EXISTS ciphers
		(Host text, SSLv2 text, SSLv3 text, TLSv10 text, TLSv11 text, TLSv12 text)''')
	try:
		for inputFile in inputFileList:
			with open(inputFile, 'r') as file:
				# skip the first line because it contains the string "ssl-enum-ciphers" 
				# https://stackoverflow.com/questions/4796764/read-file-from-line-2-or-skip-header-row
				file.readline()
				
				# read the rest of the file after skiiping first line
				s = file.read()

				# get rid of extra spaceswhen using older versions of nmap
				s = re.sub("\n*PORT", "PORT", s)
	
				# split on blank lines, this separates each IP in the nmap output
				hosts = re.split('\n\s*\n', s) 

				
				for host in hosts:
					if 'ssl-enum-ciphers' in host: #check if this had any output from nmap script
						ip = None
						try:
							# tries to find an IP address inside of parentheses
							# the IP ends up inside of parentheses when hostnames are scanned vs. IPs
							ip = re.search("\(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\)", host, re.M).group(0)[1:-1]
						except Exception as e:
							pass
						try:
							# try to find the IP not inside of parentheses
							ip = re.search("((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)", host, re.M).group(0)
						except Exception as e:
							pass
						"""
						try:
							try:
								# tries to find an IP address inside of parentheses
								ip = re.search("\(((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\)", host, re.M).group(0)[1:-1]
							except Exception as e: 
								#(means it didn't find an IP inside of parentheses, probably due to no hostname being passed in, let's look the old way now)
								ip = re.search("((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)", host, re.M).group(0)
							#debugging 8-6-17
							#ip = re.findall("[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", host, re.DOTALL)
							#print ip
							#exit()
						except Exception as e:
							print "host is " + host
							print "exception is " + str(e)
							print "No IP found! I'm going to die now!"
							exit() #debug
						"""
						if ip is None:
							# means both the regexes above failed
							print "host is " + host
							print "exception is " + str(e)
							print "No IP found! I'm going to die now!"
							exit() #debug
		
						ciphers = re.findall("([A-Za-z0-9/\-\(\) ]+\n\| ssl-enum-ciphers(.*?)(least strength|\|_.*SSL2[\w]+_[\w]+))", host, re.DOTALL)
						for i in range(0, len(ciphers)):
							cipher = ciphers[i][0]
							"""
							Here is an example of what "cipher" is:
								443/tcp open  https
								| ssl-enum-ciphers: 
								|   SSLv3: 
								|     ciphers: 
								|       TLS_RSA_WITH_3DES_EDE_CBC_SHA (rsa 2048) - C
								|       TLS_RSA_WITH_RC4_128_SHA (rsa 2048) - C
								|       TLS_RSA_WITH_RC4_128_MD5 (rsa 2048) - C
								|     compressors: 
								|       NULL
								|     cipher preference: server
								|     warnings: 
								|       64-bit block cipher 3DES vulnerable to SWEET32 attack
								|       Broken cipher RC4 is deprecated by RFC 7465
								|       CBC-mode cipher in SSLv3 (CVE-2014-3566)
								|       Ciphersuite uses MD5 for message integrity
								|_  least strength: C
							##	| sslv2: 
							##	|   SSLv2 supported
							##	|   ciphers: 
							##	|     SSL2_RC4_128_WITH_MD5
							##	|_    SSL2_DES_192_EDE3_CBC_WITH_MD5
							"""
	
							try:
								# grab the port
								port = re.search('(\d+)', cipher).group(0) #example: '3998/tcp open   dnx\n| ssl-enum-ciphers'
							except:
								print "cipher is: "
								print cipher
								print "exception is " + str(e)
								print "No Port found! I'm going to die now!"
								exit()
							vulnHost = "{0}:{1}".format(ip, port)
							print "{0}Processing ciphers for {1}".format(greenText, vulnHost)
				
							# create a blank entry in the database for the current host/port
							row = (vulnHost, '-', '-', '-', '-', '-')
							c.execute('INSERT INTO ciphers VALUES (?,?,?,?,?,?)', row)

							# loop over all the cipherTypes except the first (SSLv2)
							# we skip v2 here because it is addressed separately
							for cipherType in cipherTypes[1:]:

								# see if there vulnerable ciphers for the current cipherType
								vulnCiphers = getCiphers(cipherType, cipher)
								if vulnCiphers == "":
									vulnCiphers = '-'

								# no dot in the column names
								cipherType = cipherType.replace(".", "")

								# update the database for this host/port with the vulnerable ciphersa
								query = "UPDATE ciphers SET '{0}' = '{1}' WHERE Host = '{2}'".format(cipherType, vulnCiphers, vulnHost)
								c.execute(query)
							
							if 'SSLv2 supported' in cipher: 
								"""we're only checking SSLv2 if ssl-enum-ciphers also had output, 
								this means we'll miss any hosts which support ONLY SSLv2 (highly unlikely scenario)
								"""
								try:
									# this matches all the lines with 2 hash marks in the abocve example
									sslv2ciphers = re.findall("(sslv2(.*?)\|_.*SSL2[\w]+_[\w]+)", cipher, re.DOTALL)
									sslv2ciphers = sslv2ciphers[0][0]
								except Exception, e:
									print "EXCEPTION " + str(e)
									print "DEBUG SSLV2 CIPHERS " + str(sslv2ciphers)
									print "DEBUG CIPHER " + cipher
									#print "DEBUG HOST " + host
									#print "DEBUG CIPHERS " + str(ciphers)
								vulnCiphers = getCiphersSSLv2(sslv2ciphers)
								query = "UPDATE ciphers SET 'SSLv2' = '{0}' WHERE Host = '{1}'".format(vulnCiphers, vulnHost)
								c.execute(query)

							# need to incrememnt by 2 because the there are 2 match groups in ciphers
							i = i + 2
	except Exception, e:
		print str(e)
		traceback.print_exc(file=sys.stdout)
		print "{0}Could not process file {1}".format(redText, inputFile)


	try:
		# delete empty rows
		c.execute('''DELETE FROM ciphers
					WHERE SSLv2 = '-' 
					AND SSLv3 = '-'
					AND TLSv10 = '-'
					AND TLSv11 = '-'
					AND TLSv12 = '-'
					''')
		conn.commit()

		# use distinct to get rid of duplicate rows 
		# http://www.sqlitetutorial.net/sqlite-select-distinct	
		c.execute("SELECT DISTINCT * FROM ciphers") 

		# save results to file
		with open(outputFile, 'wb') as f:
			writer = csv.writer(f)
			writer.writerow(["Host:Port", "SSLv2", "SSLv3", "TLSv1.0", "TLSv1.1", "TLSv1.2"])
			writer.writerows(c.fetchall())
			print "{0}Results dumped to {1}".format(blueText, outputFile)

		# print affected systems to screen
		c.execute('''SELECT Host from ciphers''')
		# fetchall returns a list of tuples of length 1
		print "\n\nUse this to add affected systems to rmaker"
		for row in c.fetchall():
			print row[0].replace(':',', ,(') + '/tcp)'
	except:
		pass

	# remove temporary database
	if deleteDb is True:
		os.remove(db)

def args():
	# use nargs to get unlimited number of files as input
	# https://stackoverflow.com/questions/17813273/infinite-amount-of-command-line-arguments-in-python
	p = argparse.ArgumentParser(description="Create Table from Nmap Ciphers")
	group = p.add_mutually_exclusive_group(required=True)
	group.add_argument("--nmap", "-i", required=False, nargs="+", metavar="<nmap-input-filename(s)>", 
						help='File(s) containing Nmap script output. \
						This file should be generated with the following command: \
						"nmap -iL customer-ips.txt --script ssl-enum-ciphers,sslv2 -oN customer.ciphers"')
	group.add_argument("--ips", "-l", required=False, metavar="<list-of-ips>", 
						help="File containing a newline separeted list of IPs to be scanned. \
						Drops nmap cipher script output files in current directory")
	p.add_argument("--iterations", "-n", default=3, required=False, metavar="<number-of-iterations>", 
						help="Number of times to run ssl-enumer-ciphers against \
						the provided list of ips (default 3)")
	p.add_argument("--output", "-o", default="output-<date/time>.csv", 
					required=False, metavar="<output-filename>", 
					help='The name of the csv file that will be generated. Default is "output.csv"')
	p.add_argument("--noping", "-p", action='store_true', help="Don't ping the target hosts.")
	p.add_argument("--deletedb", "-d", default=True, required=False, action='store_false', 
					help="Delete the temporary sqlite database")

	# https://stackoverflow.com/questions/6722936/python-argparse-make-at-least-one-argument-required
	args = p.parse_args()
	if (args.nmap is None and args.ips is None):
		p.error("{0}No action requested, add --nmap or --ips".format(redText))
	if (args.nmap and args.ips):
		p.error("{0}Please specify ONLY --nmap OR --ips, not both".format(redText))
		#parser.print_help()
	if (args.ips):
		if (not os.path.exists(args.ips)):
			p.error("{0}{1} is not a valid file -- List of IPs should be a valid file".format(redText, args.ips))
	if (args.nmap):
		for inputFile in args.nmap:
			if (not os.path.exists(inputFile)):
				p.error("{0}{1} is not a valid file -- Nmap output being parsed should be a valid file".format(redText, inputFile))
				#p.error("Nmap output being parsed should be a valid file")
	try:
		args.iterations = int(args.iterations)
		if (args.iterations <= 0):
			p.error("{0}iterations must be a positive and non-zero integer!".format(redText))
		#parser.print_help()
	except:
			p.error("{0}iterations must be a positive and non-zero integer!".format(redText))
	return args

#def main():
args = args()
if (args.output):
	outputFile = args.output
if (args.output == "output-<date/time>.csv"):
	outputFile = "output-{0}.csv".format(datetime.datetime.fromtimestamp(time.time()).strftime('%m-%d-%Y-%H-%M-%S'))

if (args.nmap):
	parseResults(args.nmap, outputFile, args.deletedb) #run against the list of files that they provided
if (args.ips):
	uniqIps = "/tmp/{0}.uniq".format(uuid.uuid4())
	with open(uniqIps, "w") as text_file:
		with open(args.ips, 'r') as ips:
			for ip in set(ips.readlines()):
				text_file.write(ip)
	for i in range(0, args.iterations):
		print "{0}Running nmap scan #{1}".format(greenText, i+1)
		nmap(uniqIps, args.noping) #run the nmap cipher script and create the output files in current directory

	# inputFileList will be a list of ".ciphers" files from the current directory
	# ['1.ciphers', '2.ciphers']
	# https://stackoverflow.com/questions/3207219/how-do-i-list-all-files-of-a-directory
	inputFileList = glob.glob("*.ciphers")
	parseResults(inputFileList, outputFile)
try:
	os.remove(uniqIps)
except Exception:
	pass #uniqIps only gets created if they passed in a list of IPs vs. nmap file
#main()

