__author__ = 'Syver Døving Agdestein'


import numpy as np
from fenics import *
import matplotlib.pyplot as plt
from scipy.interpolate import interp1d

import conservation_solver as cs


class Artery(object):
	""" Represent an artery.
	:param Ru: Upstream radius
	:param Rd: Downstream radius
	:param L: Vessel length
	:param k: Vector containing k1, k2 and k3 from the relation Eh/R0
	:param Re: Reynolds number
	:param p0: Diastolic pressure
	"""
	def __init__(self, Ru, Rd, L, k1, k2, k3, Re, p0, R1, R2, CT):
		""" Construct artery.
		Add its intrinsic characteristics, not its numerical solution.
		"""
		self.Ru = Ru
		self.Rd = Rd
		self.L = L
		self.k1 = k1
		self.k2 = k2
		self.k3 = k3
		self.Re = Re
		self.p0 = p0
		self.R1 = R1
		self.R2 = R2
		self.CT = CT


	def solve(self, Nx, Nt, T, N_cycles):
		"""Compute the solution.
		:param Nx: Number of spatial steps
		:param Nt: Number of temporal steps
		:param T: Duration of one cardiac cycle
		:param N_cycles: Number of cardiac cycles
		"""
		self.Nx = Nx
		self.Nt = Nt
		self.T = T
		self.N_cycles = N_cycles
		self.mesh = IntervalMesh(Nx, 0, L)
		self.elV = FiniteElement('CG', mesh.ufl_cell(), 1)
		self.V = FunctionSpace(mesh, elV)
		self.V2 = FunctionSpace(mesh, elV*elV)

		# Define trial function
		U = Function(V2)
		A, q = split(U)

		# Define test functions
		v1, v2 = TestFunctions(V2)

		# Initial vessel-radius and deduced quantities
		r0 = Expression('ru*pow(rd/ru, x[0]/L)',
			degree=2, ru=self.ru, rd=self.rd, L=self.L)
		A0 = Expression('pi*pow(ru, 2)*pow(rd/ru, 2*x[0]/L)',
			degree=2, ru=self.ru, rd=self.rd, L=self.L)
		f = Expression('4/3*Eh/ru/pow(ru/rd, x[0]/L)',
			degree=2, ru=self.ru, rd=self.rd, L=self.L, Eh=self.Eh)
		dfdr = Expression('4/3*k1*k2*exp(k2*ru*pow(rd/ru, x[0]/L))',
			degree=2, ru=self.ru, rd=self.rd, L=self.L, k1=self.k1, k2=self.k2)
		drdx = Expression('log(rd/ru)/L*ru*pow(rd/ru, x[0]/L)',
			degree=2, ru=self.ru, rd=self.rd, L=self.L)

		# Inlet flow
		q_in = Function(V)
		q_in.assign(Constant(q_ins[0]))

		# Outlet area
		A_out = Function(V)
		A_out.assign(Constant(A0(L)))

		# The initial value of the trial function is deduced from the bottom boundary conditions
		U_n = Function(V2)
		U_n.assign(Expression(('pi*pow(ru, 2)*pow(rd/ru, 2*x[0]/L)', 'q00'),
			degree=2, ru=ru, rd=rd, L=L, q00=q_ins[0]))
		
		# Array for storing the solution
		self.solution = [0]*Nt
		for n in range(Nt):
			self.solution[n] = Function(V2)
		self.solution[0].assign(U_n)

		# Spatial boundary conditions
		tol = 1.e-14
		def inlet_bdry(x, on_boundary):
			return on_boundary and near(x[0], 0, tol)
		def outlet_bdry(x, on_boundary):
			return on_boundary and near(x[0], L, tol)
		bc_outlet = DirichletBC(V2.sub(0), A_out, outlet_bdry)
		bc_inlet = DirichletBC(V2.sub(1), q_in, inlet_bdry)
		bcs = [bc_inlet, bc_outlet]

		# Variational form
		self.FF = A*v1*dx\
		   + q*v2*dx\
		   + dt*grad(q)[0]*v1*dx\
		   + dt*(pow(q, 2)/(A+DOLFIN_EPS)+f*sqrt(A0*(A+DOLFIN_EPS)))*v2*ds\
		   - dt*(pow(q, 2)/(A+DOLFIN_EPS)+f*sqrt(A0*(A+DOLFIN_EPS)))*grad(v2)[0]*dx\
		   + dt*2*sqrt(pi)/db/Re*q/sqrt(A+DOLFIN_EPS)*v2*dx\
		   - dt*(2*sqrt(A+DOLFIN_EPS)*(sqrt(pi)*f+sqrt(A0)*dfdr)-(A+DOLFIN_EPS)*dfdr)*drdx*v2*dx\
		   - U_n[0]*v1*dx\
		   - U_n[1]*v2*dx

		# Progress bar
		progress = Progress('Time-stepping')
		set_log_level(PROGRESS)

		# Time
		t = 0

		for n_cycle in range(N_cycles):

			# Time-stepping
			for n in range(Nt-1):

				print('Iteration '+str(n))

				t += dt

				# U_n+1 is solution of FF == 0
				solve(FF == 0, U, bcs)

				# Update previous solution
				U_n.assign(U)

				# Update inlet boundary condition
				q_in.assign(Constant(qq[n]))

				# Update outlet boundary condition
				A_out_value = compute_A_out(U_n)
				A_out.assign(Constant(A_out_value))
				
				# Store solution at time t_(n+1)
				self.solution[n+1].assign(U)

				# Update progress bar
				progress.update((t+dt)/N_cycles/T)


	def F_from_equation(U, x):
		"""Compute the flux term.
		:param U: Value of the solution
		:param x: Point
		"""
		return np.array([U[1], U[1]**2 + f(x)*np.sqrt(A0(x)*U[0])])

	def S_from_equation(U, x):
		"""Compute the source term.
		:param U: Value of the solution
		:param x: Point
		"""
		return np.array([0, -2*np.sqrt(np.pi)/db/Re*U[1]/np.sqrt(U[0])\
			+(2*np.sqrt(U[0])*(np.sqrt(np.pi)*f(x)\
			+np.sqrt(A0(x))*dfdr(x))-U[0]*dfdr(x))*drdx(x)])

	def compute_A_out(U_n, k_max=100, tol=1.0e-7):
		"""Compute the outlet boundary value of A at time step t_(n+1).
		:param U_n: Solution (function) at time step t_n
		:param k_max: Maximum number of iterations in Piccards scheme
		:param tol: Tolerance for Piccards fixed point iteration scheme
		"""
		# Spatial step, many times larger than the one used in the finite elements scheme (to ensure convergence).
		deltax = 10*L/Nx
		x2, x1, x0 = L-2*deltax, L-deltax, L
		x21, x10 = L-1.5*deltax, L-0.5*deltax

		Um2, Um1, Um0 = U_n(x2), U_n(x1), U_n(x0)

		# Values at time step n
		Fm2, Sm2 = F_from_equation(Um2, x2), S_from_equation(Um2, x2)
		Fm1, Sm1 = F_from_equation(Um1, x1), S_from_equation(Um1, x1)
		Fm0, Sm0 = F_from_equation(Um0, x0), S_from_equation(Um0, x0)

		# Values at time step n+1/2
		U_half_21 = (Um1+Um2)/2 - dt/deltax*(Fm1-Fm2) + dt/4*(Sm1+Sm2)
		U_half_10 = (Um0+Um1)/2 - dt/deltax*(Fm0-Fm1) + dt/4*(Sm0+Sm1)
		F_half_21, S_half_21 = F_from_equation(U_half_21, x21), S_from_equation(U_half_21, x21)
		F_half_10, S_half_10 = F_from_equation(U_half_10, x10), S_from_equation(U_half_10, x10)

		# Value at time step n+1
		qm1 = Um1[1] - dt/deltax*(F_half_10[1]-F_half_21[1]) + dt/2*(S_half_10[1]+S_half_21[1])

		# Fixed point iteration
		pn = p0 + f(L)*(1-np.sqrt(A0(L)/Um0[0]))
		p = pn
		for k in range(k_max):
			p_old = p
			qm0 = Um0[1] + (p-pn)/R1 + dt/R1/R2/CT*pn - dt*(R1+R2)/R1/R2/CT*Um0[1]
			Am0 = Um0[0] - dt/deltax*(qm0-qm1)
			p = p0 + f(L)*(1-np.sqrt(A0(L)/Am0))
			if abs(p-p_old) < tol:
				break

		return Am0


class Artery_Network(object):
	"""Describe a network of arteries.
	:param order: Number of arterial levels
	:param Ru: Upstream radii
	:param Rd: Downstream radii
	:param L: Vessel lengths
	:param k: Vectors containing k1, k2 and k3 from the relation Eh/R0
	:param Re: Reynolds number
	:param p0: Diastolic pressure
	"""
	def __init__(self, order, Ru, Rd, L, k1, k2, k3, Re, p0):
		self.order = order
		self.arteries = [0] * (2**order-1)
		for i in range(len(arteries)):
			arteries[i] = Artery(Ru[i], Rd[i], L[i], k1[i], k2[i], k3[i], Re, p0)


	def solve(self, Nx, Nt, T, q_in):
		"""Solve the equation on the entire arterial network.
		:param Nx: Number of spatial steps
		:param Nt: Number of temporal steps
		:param T: Period of one cardiac cycle
		:param q_in: Vector of inlet flow for the first artery.
		"""
		for i in range(len(arteries)):
			arteries[i].define_problem(Nx, Nt, T)
			arteries[i].solve(q_in)
