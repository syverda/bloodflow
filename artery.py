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
	def __init__(self, Ru, Rd, L, k1, k2, k3, nu, p0, R1, R2, CT):
		""" Construct artery.
		Add its intrinsic characteristics, not its numerical solution.
		"""
		self.Ru = Ru
		self.Rd = Rd
		self.L = L
		self.k1 = k1
		self.k2 = k2
		self.k3 = k3
		self.nu = nu
		self.Re = 10.0/nu/1.0
		self.p0 = p0
		self.R1 = R1
		self.R2 = R2
		self.CT = CT


	def define_geometry(self, Nx, Nt, T, N_cycles):
		"""Define FEniCS parameters.
		Compute the solution.
		:param Nx: Number of spatial steps
		:param Nt: Number of temporal steps
		:param T: Duration of one cardiac cycle
		:param N_cycles: Number of cardiac cycles
		"""
		self.Nx = Nx
		self.Nt = Nt
		self.T = T
		self.N_cycles = N_cycles
		
		self.dt = self.T/self.Nt
		self.db = np.sqrt(self.nu*self.T/2/np.pi)
		
		self.mesh = IntervalMesh(self.Nx, 0, self.L)
		self.elV = FiniteElement('CG', self.mesh.ufl_cell(), 1)
		self.V = FunctionSpace(self.mesh, self.elV)
		self.V2 = FunctionSpace(self.mesh, self.elV*self.elV)

		# Initial vessel-radius and deduced quantities
		self.r0 = Expression('Ru*pow(Rd/Ru, x[0]/L)',
							degree=2, Ru=self.Ru, Rd=self.Rd, L=self.L)
		self.A0 = Expression('pi*pow(Ru, 2)*pow(Rd/Ru, 2*x[0]/L)',
							degree=2, Ru=self.Ru, Rd=self.Rd, L=self.L)
		self.f = Expression('4/3*(k1*exp(k2*Ru*pow(Ru/Rd, x[0]/L)) + k3)',
							degree=2, Ru=self.Ru, Rd=self.Rd, L=self.L,
							k1=self.k1, k2=self.k2, k3=self.k3)
		self.dfdr = Expression('4/3*k1*k2*exp(k2*Ru*pow(Rd/Ru, x[0]/L))',
						 	   degree=2, Ru=self.Ru, Rd=self.Rd, L=self.L,
							   k1=self.k1, k2=self.k2)
		self.drdx = Expression('log(Rd/Ru)/L*Ru*pow(Rd/Ru, x[0]/L)',
							   degree=2, Ru=self.Ru, Rd=self.Rd, L=self.L)
		
		# Array for storing the solution
		self.solution = [0]*Nt
		for n in range(Nt):
			self.solution[n] = Function(self.V2)

	
	def solve(self, q_ins):
		"""Compute and store the solution to dU/dt + dF/dx = S.
		:param artery a: Artery on which the solution is to be computed
		:param q_ins: Vector containing inlet flow
		"""
		cs_object = cs.Conservation_Solver()
		cs.solve(self, q_ins)

	def pressure(self, f, A0, A):
		""" Compute the pressure at a given point x and time t.
		:param f: Value of f(r0) in x
		:param A0: Value of A0 in x
		:param A: Area in x at a given time t
		:return: Pressure in x at time t
		"""
		return self.p0 + f*(1-np.sqrt(A0/A))

	def outlet_pressure(self, A):
		""" Compute the outlet pressure at a given time t.
		:param A: Area at a given time t
		:return: Pressure in L at time t
		"""
		return self.p0 + self.f(L)*(1-np.sqrt(self.A0(L)/A))

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


	def solve(self, Nx, Nt, T, N_cycles, q_in):
		"""Solve the equation on the entire arterial network.
		:param Nx: Number of spatial steps
		:param Nt: Number of temporal steps
		:param T: Period of one cardiac cycle
		:param N_cycles: Number of cardiac cycles
		:param q_in: Vector of inlet flow for the first artery.
		"""
		for i in range(len(arteries)):
			arteries[i].define_geometry(Nx, Nt, T, N_cycles)
			cs.solve(arteries[i], q_ins)

