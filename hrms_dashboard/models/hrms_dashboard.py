# -*- coding: utf-8 -*-
###################################################################################
#    A part of Open HRMS Project <https://www.openhrms.com>
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2018-TODAY Cybrosys Technologies (<https://www.cybrosys.com>).
#    Author: Aswani PC, Saritha Sahadevan (<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
###################################################################################
import logging
import pandas as pd
from datetime import timedelta, datetime, date
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.http import request
from odoo.tools import float_utils

_logger = logging.getLogger(__name__)

try:
    import pandas as pd
except ImportError:
    _logger.warning("The `pandas` Python module is not installed. Please install the `pandas` Python module")


class Employee(models.Model):
    _inherit = 'hr.employee'

    birthday = fields.Date('Date of Birth', groups="base.group_user")

    @api.model
    def get_user_employee_details(self):
        uid = request.session.uid
        employee = self.env['hr.employee'].sudo().search_read([('user_id', '=', uid)], limit=1)
        leaves_to_approve = self.env['hr.holidays'].sudo().search_count([('state', 'in', ['confirm', 'validate1']),
                                                                         ('type', '=', 'remove')])
        today = datetime.strftime(datetime.today(), '%Y-%m-%d')
        query = """
        select count(id)
        from hr_holidays
        WHERE (hr_holidays.date_from::DATE,hr_holidays.date_to::DATE) OVERLAPS ('%s', '%s') and type='remove' and 
        state='validate'""" % (today, today)
        cr = self._cr
        cr.execute(query)
        leaves_today = cr.fetchall()
        first_day = date.today().replace(day=1)
        last_day = (date.today() + relativedelta(months=1, day=1)) - timedelta(1)
        query = """
                select count(id)
                from hr_holidays
                WHERE (hr_holidays.date_from::DATE,hr_holidays.date_to::DATE) OVERLAPS ('%s', '%s') and type='remove' 
                and  state='validate'""" % (first_day, last_day)
        cr = self._cr
        cr.execute(query)
        leaves_this_month = cr.fetchall()
        leaves_alloc_req = self.env['hr.holidays'].sudo().search_count([('state', 'in', ['confirm', 'validate1']),
                                                                        ('type', '=', 'add')])
        timesheet_count = self.env['account.analytic.line'].sudo().search_count(
            [('project_id', '!=', False), ('user_id', '=', uid)])
        timesheet_view_id = self.env.ref('hr_timesheet.hr_timesheet_line_search')
        job_applications = self.env['hr.applicant'].sudo().search_count([])
        if employee:
            sql = """select broad_factor from hr_employee_broad_factor where id =%s"""
            self.env.cr.execute(sql, (employee[0]['id'],))
            result = self.env.cr.dictfetchall()
            broad_factor = result[0]['broad_factor']
            if employee[0]['birthday']:
                diff = relativedelta(datetime.today(), datetime.strptime(employee[0]['birthday'], '%Y-%m-%d'))
                age = diff.years
            else:
                age = False
            if employee[0]['joining_date']:
                diff = relativedelta(datetime.today(), datetime.strptime(employee[0]['joining_date'], '%Y-%m-%d'))
                years = diff.years
                months = diff.months
                days = diff.days
                experience = '{} years {} months {} days'.format(years, months, days)
            else:
                experience = False
            if employee:
                data = {
                    'broad_factor': broad_factor if broad_factor else 0,
                    'leaves_to_approve': leaves_to_approve,
                    'leaves_today': leaves_today,
                    'leaves_this_month':leaves_this_month,
                    'leaves_alloc_req': leaves_alloc_req,
                    'emp_timesheets': timesheet_count,
                    'job_applications': job_applications,
                    'timesheet_view_id': timesheet_view_id,
                    'experience': experience,
                    'age': age
                }
                employee[0].update(data)
            return employee
        else:
            return False

    @api.model
    def get_upcoming(self):
        cr = self._cr
        uid = request.session.uid
        employee = self.env['hr.employee'].search([('user_id', '=', uid)], limit=1)
        department = employee.department_id
        job_id = employee.job_id
        cr.execute("""select *, 
        (to_char(dob,'ddd')::int-to_char(now(),'ddd')::int+total_days)%total_days as dif
        from (select he.id, he.name, to_char(he.birthday, 'Month dd') as birthday,
        hj.name as job_id , he.birthday as dob,
        (to_char((to_char(now(),'yyyy')||'-12-31')::date,'ddd')::int) as total_days
        FROM hr_employee he
        join hr_job hj
        on hj.id = he.job_id
        ) birth
        where (to_char(dob,'ddd')::int-to_char(now(),'DDD')::int+total_days)%total_days between 0 and 15
        order by dif;""")
        birthday = cr.fetchall()
        cr.execute("""select e.name, e.date_begin, e.date_end, rc.name as location , e.is_online 
        from event_event e
        left join res_partner rp
        on e.address_id = rp.id
        left join res_country rc
        on rc.id = rp.country_id
        where e.state ='confirm'
        and (e.date_begin >= now()
        and e.date_begin <= now() + interval '15 day')
        or (e.date_end >= now()
        and e.date_end <= now() + interval '15 day')
        order by e.date_begin """)
        event = cr.fetchall()
        sql = """select ha.name, ha.announcement_reason
        from hr_announcement ha
        left join hr_employee_announcements hea
        on hea.announcement = ha.id
        left join hr_department_announcements hda
        on hda.announcement = ha.id
        left join hr_job_position_announcements hpa
        on hpa.announcement = ha.id
        where ha.state = 'approved' and 
        ha.date_start <= now()::date and
        ha.date_end >= now()::date and
        (ha.is_announcement = True or
        (ha.is_announcement = False
        and ha.announcement_type = 'employee'
        and hea.employee = %s)""" % employee.id
        if department:
            sql += """ or
            (ha.is_announcement = False and
            ha.announcement_type = 'department'
            and hda.department = %s)""" % department.id
        if job_id:
            sql += """ or
            (ha.is_announcement = False and
            ha.announcement_type = 'job_position'
            and hpa.job_position = %s)""" % job_id.id
        sql += ')'
        cr.execute(sql)
        announcement = cr.fetchall()
        return {
            'birthday': birthday,
            'event': event,
            'announcement': announcement
        }

    @api.model
    def get_dept_employee(self):
        cr = self._cr
        cr.execute(
            'select department_id, hr_department.name,count(*) from hr_employee join hr_department on hr_department.id=hr_employee.department_id group by hr_employee.department_id,hr_department.name')
        dat = cr.fetchall()
        data = []
        for i in range(0, len(dat)):
            data.append({'label': dat[i][1], 'value': dat[i][2]})
        return data

    @api.model
    def get_broad_factor(self):
        emp_broad_factor = []
        sql = """select * from hr_employee_broad_factor"""
        self.env.cr.execute(sql)
        results = self.env.cr.dictfetchall()
        for data in results:
            broad_factor = data['broad_factor'] if data['broad_factor'] else 0
            if data['broad_factor']:
                vals = {
                    'id': data['id'],
                    'name': data['name'],
                    'broad_factor': broad_factor
                }
                emp_broad_factor.append(vals)
        return emp_broad_factor

    @api.model
    def get_department_leave(self):
        month_list = []
        graph_result = []
        for i in range(5, -1, -1):
            last_month = datetime.now() - relativedelta(months=i)
            text = format(last_month, '%B %Y')
            month_list.append(text)
        self.env.cr.execute("""select id, name from hr_department""")
        departments = self.env.cr.dictfetchall()
        department_list = [x['name'] for x in departments]
        for month in month_list:
            leave = {}
            for dept in departments:
                leave[dept['name']] = 0
            vals = {
                'l_month': month,
                'leave': leave
            }
            graph_result.append(vals)
        sql = """
        SELECT h.id, h.employee_id,h.department_id
             , extract('month' FROM y)::int AS leave_month
             , to_char(y, 'Month YYYY') as month_year
             , GREATEST(y                    , h.date_from) AS date_from
             , LEAST   (y + interval '1 month', h.date_to)   AS date_to
        FROM  (select * from hr_holidays where type = 'remove' and state = 'validate') h
             , generate_series(date_trunc('month', date_from::timestamp)
                             , date_trunc('month', date_to::timestamp)
                             , interval '1 month') y
        where date_trunc('month', GREATEST(y , h.date_from)) >= date_trunc('month', now()) - interval '6 month' and
        date_trunc('month', GREATEST(y , h.date_from)) <= date_trunc('month', now()) 
        and h.department_id is not null
        """
        self.env.cr.execute(sql)
        results = self.env.cr.dictfetchall()
        leave_lines = []
        for line in results:
            employee = self.browse(line['employee_id'])
            from_dt = fields.Datetime.from_string(line['date_from'])
            to_dt = fields.Datetime.from_string(line['date_to'])
            days = employee.get_work_days_dashboard(from_dt, to_dt)
            line['days'] = days
            vals = {
                'department': line['department_id'],
                'l_month': line['month_year'],
                'days': days
            }
            leave_lines.append(vals)
        if leave_lines:
            df = pd.DataFrame(leave_lines)
            rf = df.groupby(['l_month', 'department']).sum()
            result_lines = rf.to_dict('index')
            for month in month_list:
                for line in result_lines:
                    if month.replace(' ', '') == line[0].replace(' ', ''):
                        match = list(filter(lambda d: d['l_month'] in [month], graph_result))[0]['leave']
                        dept_name = self.env['hr.department'].browse(line[1]).name
                        if match:
                            match[dept_name] = result_lines[line]['days']
        for result in graph_result:
            result['l_month'] = result['l_month'].split(' ')[:1][0].strip()[:3] + " " + result['l_month'].split(' ')[1:2][0]
        return graph_result, department_list

    def get_work_days_dashboard(self, from_datetime, to_datetime, calendar=None):
        days_count = 0.0
        total_work_time = timedelta()
        calendar = calendar or self.resource_calendar_id
        for day_intervals in calendar._iter_work_intervals(
                from_datetime, to_datetime, self.resource_id.id,
                compute_leaves=False):
            theoric_hours = self.get_day_work_hours_count(day_intervals[0][0].date(), calendar=calendar)
            work_time = sum((interval[1] - interval[0] for interval in day_intervals), timedelta())
            total_work_time += work_time
            if theoric_hours:
                days_count += float_utils.round((work_time.total_seconds() / 3600 / theoric_hours) * 4) / 4
        return days_count

    @api.model
    def employee_leave_trend(self):
        leave_lines = []
        month_list = []
        graph_result = []
        for i in range(5, -1, -1):
            last_month = datetime.now() - relativedelta(months=i)
            text = format(last_month, '%B %Y')
            month_list.append(text)
        uid = request.session.uid
        employee = self.env['hr.employee'].sudo().search_read([('user_id', '=', uid)], limit=1)
        for month in month_list:
            vals = {
                'l_month': month,
                'leave': 0
            }
            graph_result.append(vals)
        sql = """
                SELECT h.id, h.employee_id
                     , extract('month' FROM y)::int AS leave_month
                     , to_char(y, 'Month YYYY') as month_year
                     , GREATEST(y                    , h.date_from) AS date_from
                     , LEAST   (y + interval '1 month', h.date_to)   AS date_to
                FROM  (select * from hr_holidays where type = 'remove' and state = 'validate') h
                     , generate_series(date_trunc('month', date_from::timestamp)
                                     , date_trunc('month', date_to::timestamp)
                                     , interval '1 month') y
                where date_trunc('month', GREATEST(y , h.date_from)) >= date_trunc('month', now()) - interval '6 month' and
                date_trunc('month', GREATEST(y , h.date_from)) <= date_trunc('month', now()) 
                and h.employee_id = %s
                """
        self.env.cr.execute(sql, (employee[0]['id'],))
        results = self.env.cr.dictfetchall()
        for line in results:
            employee = self.browse(line['employee_id'])
            from_dt = fields.Datetime.from_string(line['date_from'])
            to_dt = fields.Datetime.from_string(line['date_to'])
            days = employee.get_work_days_dashboard(from_dt, to_dt)
            line['days'] = days
            vals = {
                'l_month': line['month_year'],
                'days': days
            }
            leave_lines.append(vals)
        if leave_lines:
            df = pd.DataFrame(leave_lines)
            rf = df.groupby(['l_month']).sum()
            result_lines = rf.to_dict('index')
            for line in result_lines:
                match = list(filter(lambda d: d['l_month'].replace(' ', '') == line.replace(' ', ''), graph_result))
                if match:
                    match[0]['leave'] = result_lines[line]['days']
        for result in graph_result:
            result['l_month'] = result['l_month'].split(' ')[:1][0].strip()[:3] + " " + result['l_month'].split(' ')[1:2][0]
        return graph_result

    @api.model
    def join_resign_trends(self):
        cr = self._cr
        month_list = []
        join_trend = []
        resign_trend = []
        for i in range(11, -1, -1):
            last_month = datetime.now() - relativedelta(months=i)
            text = format(last_month, '%B %Y')
            month_list.append(text)
        for month in month_list:
            vals = {
                'l_month': month,
                'count': 0
            }
            join_trend.append(vals)
        for month in month_list:
            vals = {
                'l_month': month,
                'count': 0
            }
            resign_trend.append(vals)
        cr.execute('''select to_char(joining_date, 'Month YYYY') as l_month, count(id) from hr_employee 
        WHERE joining_date BETWEEN CURRENT_DATE - INTERVAL '12 months'
        AND CURRENT_DATE + interval '1 month - 1 day'
        group by l_month;''')
        join_data = cr.fetchall()
        cr.execute('''select to_char(resign_date, 'Month YYYY') as l_month, count(id) from hr_employee 
        WHERE resign_date BETWEEN CURRENT_DATE - INTERVAL '12 months'
        AND CURRENT_DATE + interval '1 month - 1 day'
        group by l_month;''')
        resign_data = cr.fetchall()

        for line in join_data:
            match = list(filter(lambda d: d['l_month'].replace(' ', '') == line[0].replace(' ', ''), join_trend))
            if match:
                match[0]['count'] = line[1]
        for line in resign_data:
            match = list(filter(lambda d: d['l_month'].replace(' ', '') == line[0].replace(' ', ''), resign_trend))
            if match:
                match[0]['count'] = line[1]
        for join in join_trend:
            join['l_month'] = join['l_month'].split(' ')[:1][0].strip()[:3]
        for resign in resign_trend:
            resign['l_month'] = resign['l_month'].split(' ')[:1][0].strip()[:3]
        graph_result = [{
            'name': 'Join',
            'values': join_trend
        }, {
            'name': 'Resign',
            'values': resign_trend
        }]
        return graph_result

    @api.model
    def get_attrition_rate(self):
        month_attrition = []
        monthly_join_resign = self.join_resign_trends()
        month_join = monthly_join_resign[0]['values']
        month_resign = monthly_join_resign[1]['values']
        sql = """
        SELECT (date_trunc('month', CURRENT_DATE))::date - interval '1' month * s.a AS month_start 
        FROM generate_series(0,11,1) AS s(a);"""
        self._cr.execute(sql)
        month_start_list = self._cr.fetchall()
        for month_date in month_start_list:
            self._cr.execute("""select count(id), to_char(date '%s', 'Month YYYY') as l_month from hr_employee 
            where resign_date> date '%s' or resign_date is null and joining_date < date '%s'
            """ % (month_date[0], month_date[0], month_date[0],))
            month_emp = self._cr.fetchone()
            # month_emp = (month_emp[0], month_emp[1].split(' ')[:1][0].strip()[:3])
            match_join = list(filter(lambda d: d['l_month'] == month_emp[1].split(' ')[:1][0].strip()[:3], month_join))[0]['count']
            match_resign = list(filter(lambda d: d['l_month'] == month_emp[1].split(' ')[:1][0].strip()[:3], month_resign))[0]['count']
            month_avg = (month_emp[0]+match_join-match_resign+month_emp[0])/2
            attrition_rate = (match_resign/month_avg)*100 if month_avg != 0 else 0
            vals = {
                # 'month': month_emp[1].split(' ')[:1][0].strip()[:3] + ' ' + month_emp[1].split(' ')[-1:][0],
                'month': month_emp[1].split(' ')[:1][0].strip()[:3],
                'attrition_rate': round(float(attrition_rate), 2)
            }
            month_attrition.append(vals)
        return month_attrition
