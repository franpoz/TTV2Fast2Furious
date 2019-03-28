import numpy as np
from scipy.optimize import brenth
from scipy.special import erf
from scipy.optimize import minimize,LinearConstraint
from scipy.integrate import trapz
from .ttv_basis_functions import dt0_InnerPlanet,dt0_OuterPlanet

def PerturberPeriodPhaseToBestSigmaChiSquared(Ppert,phi,TransitData, PlanetData = None,full_output=False):
    """
    Convert a hypothetical perturber period and phase to a mean and std. deviation
    of a gaussian distribution describing the perturber mass conditional posterior.

    Arguments
    ---------
    Ppert : real
        Period of the pertuber
    phi : real
        Orbital phase of perturber
    TransitData : list (optional)
        Transit observation data given as a list of three arrays:
            TransitData = [Numbers, Times, Uncertainties]
        Default value is set to $\pi$-Mensae c's data.
    PlanetData : list of reals (optional)
        List containing transiting planet's T0 and Period.

    full_output : boole (optional)
        Include a dictionary in the function output that contains 
         the full best fit, covariance matrix, design matrix, 
         and weighted observations vector.

    Returns
    -------
    tuple of reals :
        Returns the best-fit mass, mass distribution 'sigma' and the chi-squared of
        the timing residuals.
    """

    transit_num,transit_time,transit_unc = TransitData
    assert np.alltrue(transit_num>=0)

    yvec = transit_time / transit_unc
    Ntransits = int(np.max(transit_num))
    Tpert = Ppert * phi / (2*np.pi)


    if PlanetData is None:
        Ndata = len(transit_num)
        A = np.vstack([np.ones(Ndata)/transit_unc, transit_num/transit_unc]).T
        T0,P = np.linalg.lstsq(A , yvec,rcond=-1)[0]
    else:
        T0,P = PlanetData

    if Ppert > P:
        dt0_basis_fn = dt0_InnerPlanet(P,Ppert,T0,Tpert,Ntransits+1)
    else:
        dt0_basis_fn = dt0_OuterPlanet(P,Ppert,T0,Tpert,Ntransits+1)

    bfMatrix = np.vstack([np.ones(Ntransits+1) , np.arange(Ntransits+1) , dt0_basis_fn]).T

    design_Matrix = np.array([bfMatrix[i]/transit_unc[ni]  for ni,i in enumerate(np.array(transit_num,dtype=int))])

    Sigma_matrix = np.linalg.inv(design_Matrix.T.dot(design_Matrix))
    best,chisq = np.linalg.lstsq(design_Matrix,yvec,rcond=-1)[:2]
    chisq = chisq[0]
    if best[2]<0:
        to_minimize = lambda x: (design_Matrix.dot(x)-yvec).dot((design_Matrix.dot(x)-yvec))
        x0 = np.copy(best)
        x0[2]=0
        minsoln = minimize(to_minimize,x0,constraints=[LinearConstraint(np.diag([0,0,1]),0,np.infty)])
        chisq = minsoln.fun

    if full_output:
        return best[2], np.sqrt(Sigma_matrix[2,2]) ,chisq ,dict({'best_fit':best,'CovarianceMatrix':Sigma_matrix,'DesignMatrix':design_matrix,'WeightedObsVec':yvec})

    return best[2], np.sqrt(Sigma_matrix[2,2]) ,chisq

def q_integrand(mup,mbest,sigma):
    """
    Compute the value of the integrand in the integral over phase that determines q(m).

    Arguments
    ---------

    mup : real
        The mass upper limit for which q is being computed
    mbest : real
        The best-fit mass (mhat) which sets the mean of the gaussian mass distribution. Depends on phase phi.
    sigma : real
        The std. deviation parameter of the gaussian mass distribution. Depends on phase phi.

    Returns
    -------

    real :
        The value of the integrand
    """
    num = erf(mbest / sigma / np.sqrt(2)) +  erf((mup-mbest) / sigma / np.sqrt(2))
    denom = 1 + erf(mbest / sigma / np.sqrt(2))
    return num / denom

def UnseenPerturberMassUpperLimit(Ppert,confidence_levels,TransitData ,Nphi = 50,Mmax0 = 3e-3,PlanetData = None):
    """
    Compute mass upper limit(s) on a potential perturber at a given orbital period using transit data.
    Marginalizes over possible orbital phases of the perturber.

    Arguments
    ---------
    Ppert : real
        The orbital period of the hypothetical perturbing planet

    confidence_levels : array-like
        The confidence level(s) for which to return mass upper limits.

    TransitData : list of array-like
        List containing transit observation data in the form:
            TransitData = [transit numbers, transit times, transit time uncertainties]

    Nphi : int (optional)
        Number of perturber phase points used to compute integrals for marginalizing over phase.
        Default value is Nphi=50.

    Mmax0 : real (optional)
        Initial guess of mass upper limit for root-finding purposes. All mass upper-limits are
        guessed to fall between 0 and Mmax0.

    PlanetData : list (optional)
        List containing [T0,P] where T0 is the initial transit time and P is period 
         of the traniting planet. If these values are not supplied they are computed
         from the transit data.

    Returns
    -------
    Array-like :
        List of mass upper limits and the given confidence levels.
    """

    phases = np.linspace(-np.pi,np.pi,Nphi)
    mbest,sigma,chisq = np.array([PerturberPeriodPhaseToBestSigmaChiSquared(Ppert,phase,TransitData=TransitData,PlanetData=PlanetData) for phase in phases]).T
    dchisq = chisq - np.mean(chisq)
    q_of_mup = lambda mup: trapz( q_integrand(mup,mbest,sigma) * np.exp(-0.5 * dchisq),phases) / trapz(np.exp(-0.5 * dchisq),phases)

    mups = []

    for cl in np.atleast_1d(confidence_levels):
        assert (cl < 1), "%.2f is not a valid confidence level between 0 and 1!"%cl
        while q_of_mup(Mmax0) - cl < 0:
            Mmax0 *=2
        mups.append(brenth(lambda x: q_of_mup(x) - cl,0,Mmax0))

    return np.array(mups)
