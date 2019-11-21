try:
	from io import StringIO
	from datetime import datetime as dtm
	from gc import collect as gc_purge
	from collections import OrderedDict as odict
	import yaml as y
	from pypyodbc import connect as sqlCnx
	from pandas import read_sql_query as rsq,DataFrame as pdf
	from sqlalchemy import create_engine as pgcnx, exc as alchemyEXC
	from psycopg2 import connect as pgconnect, DatabaseError,DataError as psyDataError,OperationalError,IntegrityError,ProgrammingError,InternalError
	from sqlalchemy.sql import text as alchemyText
	from pandas.core.groupby.groupby import DataError
	import ray as r
	from sqlalchemy.orm import sessionmaker
	from mysql.connector import connect as mysqlCNX, Error as mysqlErr, OperationalError as mysqlOpErr
except ImportError:
	raise ImportError(' Module(s) not installed...')

with open('dimConfig.yml') as ymlFile:
	cfg=y.safe_load(ymlFile)

def dwCNX(tinyset=False):
	uri='postgresql://' +cfg['eaedb']['user']+ ':' +cfg['eaedb']['passwd']+ '@' +cfg['eaedb']['server']+ ':' +str(int(cfg['eaedb']['port']))+ '/' +cfg['eaedb']['db']
	eaeSchema=cfg['eaedb']['schema']
	if tinyset:
		csize=cfg['pandas']['tinyset']
	else:
		csize=cfg['pandas']['bigset']
	return csize,eaeSchema,uri

def dataSession(urx):
	cnxPGX=pgcnx(urx)
	SessionClass=sessionmaker(bind=cnxPGX)
	Session=SessionClass()
	return Session

def objects_sql(urx,atype,itype):
	insList_io=[]
	cnxPGX=pgcnx(urx)
	SessionClass=sessionmaker(bind=cnxPGX)
	Session=SessionClass()
	insData=cnxPGX.execute("SELECT * FROM framework.instanceconfig WHERE isactive=true AND instancetype='" +itype+ "' AND app='" +atype+ "' ")
	colFrame_io=rsq("SELECT icode,instancetype,app,collection,s_table,rower,stg_cols,pkitab,pki_cols FROM framework.live_instancecollections() WHERE instancetype='" +itype+ "' AND app='" +atype+ "' " ,cnxPGX)
	for cnx in insData:
		dat=odict(cnx)
		insDict=odict()
		insDict['icode']=dat['instancecode']
		if itype=='mssql':
			insDict['sqlConStr']='DRIVER={'+cfg['drivers']['mssql']+'};SERVER='+dat['hostip']+','+str(int(dat['hport']))+';DATABASE='+dat['dbname']+';UID='+dat['uid']+';PWD='+dat['pwd']+';MARS_Connection=Yes'
		elif itype=='salesforce':
			insDict['sqlConStr']='salesforce'
		else:
			insDict['user']=dat['uid']
			insDict['password']=dat['pwd']
			insDict['database']=dat['dbname']
			insDict['host']=dat['hostip']
			insDict['port']=dat['hport']
		insList_io.append(insDict)
	return odict([('frame',colFrame_io),('insList',insList_io),('session',Session)])

def logError(pid,jobid,err_message,uri):
	pgx=pgcnx(uri)
	err_json={'pid':[pid],'jobid':[jobid],'error':[err_message],'error_time':[dtm.utcnow()]}
	errFrame=pdf.from_dict(err_json)
	errFrame.to_sql('errorlogs',pgx,if_exists='append',index=False,schema='framework')
	pgx.dispose()
	return None

def recordpulse(v_cfg, v_pid, v_action, v_response, pg_uri):
    if v_cfg:
        pg_x=pgcnx(pg_uri)
        pulse_frame=pdf({'pid':[v_pid],'action':[v_action],'action_response':[v_response]})
        pulse_frame.to_sql('agentpulse', pg_x, if_exists='append', index=False, schema='framework')
        pg_x.dispose()
    return None
